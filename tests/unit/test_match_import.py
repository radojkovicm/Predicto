"""Covers the risky parts of the Excel bulk-import: phase resolution by name,
duplicate detection (both against existing matches and within the same file),
and that a bad row is reported but doesn't block the good ones.
"""
from datetime import datetime, timezone
from io import BytesIO

import openpyxl

from app.models.models import Competition, Match, Phase
from app.services import match_import_service


def _make_competition_with_phase(db, phase_name="Group Stage"):
    competition = Competition(name="Test Cup", status="active")
    db.add(competition)
    db.flush()
    phase = Phase(name=phase_name, order_index=1, competition_id=competition.id)
    db.add(phase)
    db.flush()
    return competition, phase


def _workbook_bytes(rows):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Matches"
    ws.append(match_import_service.TEMPLATE_HEADERS)
    for row in rows:
        ws.append(row)
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_build_template_lists_real_phase_names(db_session):
    _, phase = _make_competition_with_phase(db_session, "Round of 16")
    wb = match_import_service.build_template_workbook([phase])
    names = [row[0] for row in wb["Valid Phases"].iter_rows(min_row=2, values_only=True)]
    assert names == ["Round of 16"]


def test_parse_upload_adds_valid_rows_and_reports_bad_ones(db_session):
    competition, phase = _make_competition_with_phase(db_session)
    db_session.commit()

    rows = [
        ["Group Stage", datetime(2026, 9, 16, 21, 0), "Bayern Munich", "bay", "PSG", "psg"],
        ["Group Stage", "2026-09-17 19:00", "Barcelona", "bar", "Inter Milan", "int"],
        ["Nonexistent Phase", datetime(2026, 9, 18, 20, 0), "Man City", "mci", "Juventus", "juv"],
    ]
    added, messages = match_import_service.parse_upload(
        db_session, _workbook_bytes(rows), competition.id
    )

    assert added == 2
    assert len(messages) == 1
    assert "Nonexistent Phase" in messages[0]

    stored = db_session.query(Match).filter(Match.competition_id == competition.id).all()
    assert {m.team1_name for m in stored} == {"Bayern Munich", "Barcelona"}


def test_parse_upload_skips_duplicate_of_existing_match(db_session):
    competition, phase = _make_competition_with_phase(db_session)
    kickoff = datetime(2026, 9, 16, 21, 0, tzinfo=timezone.utc)
    db_session.add(Match(
        phase_id=phase.id, competition_id=competition.id,
        team1_code="bay", team1_name="Bayern Munich",
        team2_code="psg", team2_name="PSG",
        kickoff_utc=kickoff,
    ))
    db_session.commit()

    rows = [["Group Stage", kickoff.replace(tzinfo=None), "Bayern Munich", "bay", "PSG", "psg"]]
    added, messages = match_import_service.parse_upload(
        db_session, _workbook_bytes(rows), competition.id
    )

    assert added == 0
    assert len(messages) == 1 and "already exists" in messages[0]
    assert db_session.query(Match).filter(Match.competition_id == competition.id).count() == 1


def test_parse_upload_skips_duplicate_within_same_file(db_session):
    competition, phase = _make_competition_with_phase(db_session)
    db_session.commit()

    row = ["Group Stage", datetime(2026, 9, 16, 21, 0), "Bayern Munich", "bay", "PSG", "psg"]
    added, messages = match_import_service.parse_upload(
        db_session, _workbook_bytes([row, row]), competition.id
    )

    assert added == 1
    assert len(messages) == 1 and "already exists" in messages[0]
