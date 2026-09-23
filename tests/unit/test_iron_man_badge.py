"""Regression test for the _check_iron_man N+1 fix: it used to run one COUNT
query per user in a Python loop; now it's a single GROUP BY. This only checks
the observable behavior (who gets the badge) stays correct after the rewrite.
"""
from datetime import datetime, timezone

from app.models.models import Competition, Match, Phase, Prediction, User
from app.services import badge_service

KICKOFF = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _make_competition(db):
    competition = Competition(name="Comp", status="active")
    db.add(competition)
    db.flush()
    return competition


def _make_user(db, username):
    user = User(username=username, password_hash="x")
    db.add(user)
    db.flush()
    return user


def _make_finished_match(db, phase_id, competition_id):
    match = Match(
        phase_id=phase_id,
        team1_code="AAA", team1_name="Team A",
        team2_code="BBB", team2_name="Team B",
        kickoff_utc=KICKOFF,
        result_goals1=1, result_goals2=0,
        is_finished=True, is_visible=True,
        competition_id=competition_id,
    )
    db.add(match)
    db.flush()
    return match


def test_iron_man_awarded_only_to_users_who_predicted_every_match_in_phase(db_session):
    competition = _make_competition(db_session)
    phase = Phase(name="Group", order_index=1, competition_id=competition.id)
    db_session.add(phase)
    db_session.flush()

    complete_user = _make_user(db_session, "complete")
    partial_user = _make_user(db_session, "partial")
    silent_user = _make_user(db_session, "silent")

    matches = [_make_finished_match(db_session, phase.id, competition.id) for _ in range(3)]

    for match in matches:
        db_session.add(Prediction(user_id=complete_user.id, match_id=match.id, pred_goals1=0, pred_goals2=0))
    # partial_user only predicts 2 of the 3 matches.
    for match in matches[:2]:
        db_session.add(Prediction(user_id=partial_user.id, match_id=match.id, pred_goals1=0, pred_goals2=0))
    db_session.commit()

    badge_service._check_iron_man(db_session, matches[-1], competition.id)
    db_session.commit()

    from app.models.models import UserBadge
    awarded_user_ids = {
        b.user_id for b in
        db_session.query(UserBadge).filter(UserBadge.badge_code == "iron_man").all()
    }

    assert awarded_user_ids == {complete_user.id}
    assert partial_user.id not in awarded_user_ids
    assert silent_user.id not in awarded_user_ids
