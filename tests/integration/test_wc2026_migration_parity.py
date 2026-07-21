"""Requirement-4 regression test: real WC2026 scores/leaderboard unchanged
after the multi-competition schema change.

Ground truth is read (read-only, never modified) from db_dump/predicto.sqlite,
a snapshot of the real production data taken before this migration. That
snapshot's schema is pre-migration (no competition_id etc.) but its VALUES
(match results, predictions, pre-existing computed points) are trustworthy.

We load that ground truth into a fresh test DB built from the CURRENT
app.models.models.Base schema (via the db_session fixture), attach everything
to one synthetic WC2026 Competition row (using the same defaults / backfill
rules migration 0008 uses), and assert:
  1. every prediction's points recomputed with the new parametrized
     compute_points() matches the ground-truth points stored in the dump.
  2. both real leagues' ranking_service.get_leaderboard() output matches an
     independently-computed expectation derived straight from the dump.

Alembic itself is intentionally NOT exercised here — running the actual
migration against a scratch copy of db_dump/predicto.sqlite is a separate
manual verification step (see the plan), not part of this automated suite.
"""
import sqlite3
from datetime import datetime
from pathlib import Path

import pytest

from app.models.models import (
    Competition, League, Match, Phase, Prediction, User, UserBadge, UserLeague,
)
from app.services import ranking_service
from app.services.scoring_service import ScoringConfig, compute_points

# db_dump/predicto.sqlite is gitignored on purpose: it's a snapshot of real
# production data (real player names/usernames/predictions). It must be
# copied manually onto any machine that needs to run this test — ask a
# maintainer for a copy.
DUMP_PATH = Path(__file__).resolve().parents[2] / "db_dump" / "predicto.sqlite"

# Same group-stage phases (order_index 1-3) migration 0008's backfill uses.
GROUP_STAGE_ORDER_INDICES = {1, 2, 3}


def _parse_dt(value):
    if value is None:
        return None
    v = value.strip()
    if v.endswith("+00"):
        v += ":00"
    return datetime.fromisoformat(v)


def _outcome(goals1: int, goals2: int) -> str:
    if goals1 > goals2:
        return "HOME"
    if goals1 == goals2:
        return "DRAW"
    return "AWAY"


def _read_dump() -> dict:
    if not DUMP_PATH.exists():
        pytest.skip(
            f"{DUMP_PATH} not found — this integration test requires a "
            "manual copy of the production data snapshot (it's gitignored "
            "because it contains real personal data); ask a maintainer for "
            "a copy and place it there to run this test."
        )
    conn = sqlite3.connect(f"file:{DUMP_PATH}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.cursor()
        data = {}
        for table in (
            "users", "leagues", "user_leagues", "phases", "matches",
            "predictions", "user_badges",
        ):
            cur.execute(f"SELECT * FROM {table}")
            data[table] = [dict(row) for row in cur.fetchall()]
        return data
    finally:
        conn.close()


def _load_wc2026(db_session, data: dict) -> Competition:
    max_finished_at = max(
        _parse_dt(m["finished_at"]) for m in data["matches"] if m["finished_at"]
    )
    competition = Competition(
        name="World Cup 2026",
        status="finished",
        finished_at=max_finished_at,
        points_outcome=10,
        points_goal_diff=7,
        points_goal_home=4,
        points_goal_away=4,
        joker_bonus=8,
        joker_penalty=-5,
        jokers_per_phase=1,
    )
    db_session.add(competition)
    db_session.flush()

    for u in data["users"]:
        db_session.add(User(
            id=u["id"],
            username=u["username"],
            password_hash=u["password_hash"],
            is_admin=bool(u["is_admin"]),
            created_at=_parse_dt(u["created_at"]),
            failed_login_attempts=u["failed_login_attempts"],
            locked_until=_parse_dt(u["locked_until"]),
            first_name=u["first_name"],
            last_name=u["last_name"],
        ))

    for p in data["phases"]:
        db_session.add(Phase(
            id=p["id"],
            name=p["name"],
            order_index=p["order_index"],
            joker_allowed=bool(p["joker_allowed"]),
            competition_id=competition.id,
            is_group_stage=p["order_index"] in GROUP_STAGE_ORDER_INDICES,
            point_multiplier=1.00,
        ))

    for l in data["leagues"]:
        db_session.add(League(
            id=l["id"],
            name=l["name"],
            join_code=l["join_code"],
            created_at=_parse_dt(l["created_at"]),
            competition_id=competition.id,
        ))

    db_session.flush()

    for ul in data["user_leagues"]:
        db_session.add(UserLeague(user_id=ul["user_id"], league_id=ul["league_id"]))

    for m in data["matches"]:
        db_session.add(Match(
            id=m["id"],
            phase_id=m["phase_id"],
            team1_code=m["team1_code"],
            team1_name=m["team1_name"],
            team2_code=m["team2_code"],
            team2_name=m["team2_name"],
            kickoff_utc=_parse_dt(m["kickoff_utc"]),
            result_goals1=m["result_goals1"],
            result_goals2=m["result_goals2"],
            is_finished=bool(m["is_finished"]),
            is_visible=bool(m["is_visible"]),
            finished_at=_parse_dt(m["finished_at"]),
            competition_id=competition.id,
        ))

    db_session.flush()

    for p in data["predictions"]:
        db_session.add(Prediction(
            id=p["id"],
            user_id=p["user_id"],
            match_id=p["match_id"],
            pred_goals1=p["pred_goals1"],
            pred_goals2=p["pred_goals2"],
            is_joker=bool(p["is_joker"]),
            points=p["points"],
            created_at=_parse_dt(p["created_at"]),
            updated_at=_parse_dt(p["updated_at"]),
        ))

    for b in data["user_badges"]:
        db_session.add(UserBadge(
            id=b["id"],
            user_id=b["user_id"],
            badge_code=b["badge_code"],
            match_id=b["match_id"],
            league_id=b["league_id"],
            awarded_at=_parse_dt(b["awarded_at"]),
            is_active=bool(b["is_active"]),
            competition_id=competition.id,
        ))

    db_session.commit()
    return competition


# ---------------------------------------------------------------------------
# 1. Every prediction's points, recomputed, match the ground truth
# ---------------------------------------------------------------------------

def test_all_predictions_points_match_ground_truth(db_session):
    data = _read_dump()
    competition = _load_wc2026(db_session, data)

    config = ScoringConfig(
        points_outcome=competition.points_outcome,
        points_goal_diff=competition.points_goal_diff,
        points_goal_home=competition.points_goal_home,
        points_goal_away=competition.points_goal_away,
        joker_bonus=competition.joker_bonus,
        joker_penalty=competition.joker_penalty,
    )

    matches_by_id = {m["id"]: m for m in data["matches"]}

    assert len(data["predictions"]) == 3157

    mismatches = []
    for p in data["predictions"]:
        match = matches_by_id[p["match_id"]]
        computed = compute_points(
            p["pred_goals1"], p["pred_goals2"],
            match["result_goals1"], match["result_goals2"],
            is_joker=bool(p["is_joker"]),
            config=config,
            point_multiplier=1.00,  # every WC2026 phase defaults to 1.00
        )
        if computed != p["points"]:
            mismatches.append((p["id"], computed, p["points"]))

    assert not mismatches, (
        f"{len(mismatches)}/{len(data['predictions'])} predictions mismatched "
        f"(id, computed, ground_truth): {mismatches[:20]}"
    )


# ---------------------------------------------------------------------------
# 2. Leaderboard for both real leagues matches an independent computation
# ---------------------------------------------------------------------------

def _expected_leaderboard(data: dict, league_id: int) -> list[dict]:
    member_ids = {
        ul["user_id"] for ul in data["user_leagues"] if ul["league_id"] == league_id
    }
    matches_by_id = {m["id"]: m for m in data["matches"]}

    preds_by_user: dict[int, list[dict]] = {}
    for p in data["predictions"]:
        if p["user_id"] in member_ids:
            preds_by_user.setdefault(p["user_id"], []).append(p)

    rows = []
    for uid in member_ids:
        preds = preds_by_user.get(uid, [])
        total_points = sum(p["points"] or 0 for p in preds)
        correct_tips = 0
        exact_scores = 0
        last_pred_at = None
        for p in preds:
            match = matches_by_id[p["match_id"]]
            if not match["is_finished"]:
                continue
            pred_outcome = _outcome(p["pred_goals1"], p["pred_goals2"])
            res_outcome = _outcome(match["result_goals1"], match["result_goals2"])
            if pred_outcome == res_outcome:
                correct_tips += 1
            if (p["pred_goals1"] == match["result_goals1"]
                    and p["pred_goals2"] == match["result_goals2"]):
                exact_scores += 1
            updated = _parse_dt(p["updated_at"])
            if updated and (last_pred_at is None or updated > last_pred_at):
                last_pred_at = updated
        rows.append({
            "user_id": uid,
            "total_points": total_points,
            "correct_tips": correct_tips,
            "exact_scores": exact_scores,
            "last_pred_at": last_pred_at,
        })

    rows.sort(key=lambda r: (
        -r["total_points"],
        -r["correct_tips"],
        -r["exact_scores"],
        r["last_pred_at"] is None,  # NULLS LAST
        r["last_pred_at"] or datetime.min,
    ))
    return rows


def _assert_leaderboard_matches(db_session, data: dict, league_id: int) -> list[dict]:
    expected = _expected_leaderboard(data, league_id)
    actual = ranking_service.get_leaderboard(db_session, league_id)

    assert len(actual) == len(expected)
    for rank, (exp, act) in enumerate(zip(expected, actual), start=1):
        assert act["rank"] == rank
        assert act["user_id"] == exp["user_id"], (rank, act, exp)
        assert act["total_points"] == exp["total_points"]
        assert act["correct_tips"] == exp["correct_tips"]
        assert act["exact_scores"] == exp["exact_scores"]
    return actual


def test_leaderboard_matches_ground_truth_league_1(db_session):
    data = _read_dump()
    _load_wc2026(db_session, data)
    _assert_leaderboard_matches(db_session, data, league_id=1)


def test_leaderboard_matches_ground_truth_league_2(db_session):
    data = _read_dump()
    _load_wc2026(db_session, data)
    actual = _assert_leaderboard_matches(db_session, data, league_id=2)

    # Extra sanity net: known real values from this session's earlier
    # season-report queries against the actual production data.
    winner = actual[0]
    assert winner["username"] == "branka.b"
    assert winner["total_points"] == 1343

    dusan = next(e for e in actual if e["username"] == "dusan.r")
    assert dusan["exact_scores"] == 20
