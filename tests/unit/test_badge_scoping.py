"""Focused tests for the new per-competition badge scoping.

Covers only what's new/risky in the multi-competition migration:
  - Hot Streak resets per competition (chunk's "reset per competition" decision).
  - group_stage_guru no longer leaks across competitions (Bug C fix).
  - League-scoped badges don't leak across a shared user's two leagues that
    live in different competitions (Bug A fix in evaluate_badges_after_result).

Synthetic, minimal fixtures — not real WC2026 data (see
tests/integration/test_wc2026_migration_parity.py for that).
"""
from datetime import datetime, timedelta

from app.models.models import Competition, League, Match, Phase, Prediction, User, UserBadge, UserLeague
from app.services import badge_service, ranking_service


def _make_competition(db, name):
    competition = Competition(name=name, status="active")
    db.add(competition)
    db.flush()
    return competition


def _make_user(db, username):
    user = User(username=username, password_hash="x")
    db.add(user)
    db.flush()
    return user


def _make_phase(db, competition_id, order_index=1, is_group_stage=False):
    phase = Phase(
        name=f"Phase {order_index}",
        order_index=order_index,
        competition_id=competition_id,
        is_group_stage=is_group_stage,
    )
    db.add(phase)
    db.flush()
    return phase


def _make_match(db, phase_id, competition_id, kickoff, result_goals1=1, result_goals2=0, is_finished=True):
    match = Match(
        phase_id=phase_id,
        team1_code="AAA", team1_name="Team A",
        team2_code="BBB", team2_name="Team B",
        kickoff_utc=kickoff,
        result_goals1=result_goals1,
        result_goals2=result_goals2,
        is_finished=is_finished,
        is_visible=True,
        competition_id=competition_id,
    )
    db.add(match)
    db.flush()
    return match


def _make_prediction(db, user_id, match_id, pred_goals1=1, pred_goals2=0, points=None, is_joker=False):
    pred = Prediction(
        user_id=user_id, match_id=match_id,
        pred_goals1=pred_goals1, pred_goals2=pred_goals2,
        is_joker=is_joker, points=points,
    )
    db.add(pred)
    db.flush()
    return pred


# ---------------------------------------------------------------------------
# Hot Streak resets per competition
# ---------------------------------------------------------------------------

def test_hot_streak_resets_per_competition(db_session):
    comp_a = _make_competition(db_session, "Comp A")
    comp_b = _make_competition(db_session, "Comp B")
    user = _make_user(db_session, "streaky")

    base = datetime(2026, 1, 1)
    for competition in (comp_a, comp_b):
        phase = _make_phase(db_session, competition.id)
        for i in range(badge_service.HOT_STREAK_LENGTH):
            match = _make_match(db_session, phase.id, competition.id, base + timedelta(days=i))
            _make_prediction(
                db_session, user.id, match.id,
                points=badge_service.HOT_STREAK_MIN_POINTS,
            )
        badge_service._check_hot_streak(db_session, user.id, competition.id)

    db_session.commit()

    hot_streak_badges = (
        db_session.query(UserBadge)
        .filter(UserBadge.user_id == user.id, UserBadge.badge_code == "hot_streak")
        .all()
    )
    assert len(hot_streak_badges) == 2
    assert {b.competition_id for b in hot_streak_badges} == {comp_a.id, comp_b.id}


# ---------------------------------------------------------------------------
# group_stage_guru doesn't leak across competitions
# ---------------------------------------------------------------------------

def test_group_stage_guru_does_not_leak_across_competitions(db_session):
    """Predictions are user-global (not league-scoped), so a league_a member
    can also have predictions on a comp_b match without being a league_b
    member. That's exactly the shape that would leak points across
    competitions under the old order_index-only signal: if group_matches
    were computed from `Phase.order_index.in_({1,2,3})` globally instead of
    `Phase.competition_id == competition_id AND Phase.is_group_stage`, the
    sum-per-user query (still correctly member_id-scoped) would silently
    pull in a member's points from the OTHER competition's same-order_index
    phase and could flip who "wins" group_stage_guru for league_a.
    """
    comp_a = _make_competition(db_session, "Comp A")
    comp_b = _make_competition(db_session, "Comp B")

    winner_a = _make_user(db_session, "winner_a")
    loser_a = _make_user(db_session, "loser_a")

    league_a = League(name="League A", competition_id=comp_a.id)
    db_session.add(league_a)
    db_session.flush()
    db_session.add_all([
        UserLeague(user_id=winner_a.id, league_id=league_a.id),
        UserLeague(user_id=loser_a.id, league_id=league_a.id),
    ])
    db_session.flush()

    # Both competitions use the SAME order_index (1) for their group-stage
    # phase, to prove order_index alone is no longer the group-stage signal.
    phase_a = _make_phase(db_session, comp_a.id, order_index=1, is_group_stage=True)
    phase_b = _make_phase(db_session, comp_b.id, order_index=1, is_group_stage=True)

    match_a = _make_match(db_session, phase_a.id, comp_a.id, datetime(2026, 1, 1))
    match_b = _make_match(db_session, phase_b.id, comp_b.id, datetime(2026, 1, 1))

    # In comp_a: winner_a clearly outscores loser_a.
    _make_prediction(db_session, winner_a.id, match_a.id, points=20)
    _make_prediction(db_session, loser_a.id, match_a.id, points=5)
    # Both also happen to have predicted comp_b's match (allowed — predictions
    # aren't restricted to a user's own leagues/competitions). Their comp_b
    # points are shaped to flip the standings if they leaked into comp_a's
    # computation: loser_a would out-total winner_a (5+99=104 vs 20+1=21).
    _make_prediction(db_session, winner_a.id, match_b.id, points=1)
    _make_prediction(db_session, loser_a.id, match_b.id, points=99)

    db_session.commit()

    badge_service._check_group_stage_guru(db_session, league_a.id, comp_a.id)
    db_session.commit()

    guru_badges = db_session.query(UserBadge).filter(UserBadge.badge_code == "group_stage_guru").all()
    by_user = {b.user_id: b for b in guru_badges}

    assert winner_a.id in by_user
    assert loser_a.id not in by_user
    assert by_user[winner_a.id].league_id == league_a.id
    assert by_user[winner_a.id].competition_id == comp_a.id


# ---------------------------------------------------------------------------
# League-scoped badges don't leak across a shared user's two leagues that
# belong to different competitions (Bug A fix).
# ---------------------------------------------------------------------------

def test_league_badges_scoped_to_matchs_competition_only(db_session):
    comp_a = _make_competition(db_session, "Comp A")
    comp_b = _make_competition(db_session, "Comp B")

    u1 = _make_user(db_session, "u1")
    u2 = _make_user(db_session, "u2")
    u3 = _make_user(db_session, "u3")
    u4 = _make_user(db_session, "u4")

    league_x = League(name="League X", competition_id=comp_a.id)
    # League Y lives in a DIFFERENT competition (B) but shares u1 as a member.
    league_y = League(name="League Y", competition_id=comp_b.id)
    db_session.add_all([league_x, league_y])
    db_session.flush()
    db_session.add_all([
        UserLeague(user_id=u1.id, league_id=league_x.id),
        UserLeague(user_id=u2.id, league_id=league_x.id),
        UserLeague(user_id=u3.id, league_id=league_x.id),
        UserLeague(user_id=u4.id, league_id=league_x.id),
        UserLeague(user_id=u1.id, league_id=league_y.id),
    ])
    db_session.flush()

    phase_a = _make_phase(db_session, comp_a.id, order_index=1)
    # Match A: result is 1-0 (HOME). Every League X member predicts a draw
    # (wrong), so all four should get "sheep" under League X.
    match_a = _make_match(db_session, phase_a.id, comp_a.id, datetime(2026, 1, 1),
                           result_goals1=1, result_goals2=0)

    predictions = [
        _make_prediction(db_session, u1.id, match_a.id, pred_goals1=0, pred_goals2=0),
        _make_prediction(db_session, u2.id, match_a.id, pred_goals1=0, pred_goals2=0),
        _make_prediction(db_session, u3.id, match_a.id, pred_goals1=0, pred_goals2=0),
        _make_prediction(db_session, u4.id, match_a.id, pred_goals1=0, pred_goals2=0),
    ]
    db_session.commit()

    badge_service.evaluate_badges_after_result(db_session, match_a, predictions, old_positions_by_league={})

    league_scoped_badges = (
        db_session.query(UserBadge)
        .filter(UserBadge.league_id.isnot(None))
        .all()
    )
    assert league_scoped_badges, "expected at least one league-scoped badge to be awarded"
    assert all(b.league_id == league_x.id for b in league_scoped_badges)
    assert all(b.competition_id == comp_a.id for b in league_scoped_badges)
    assert not any(b.league_id == league_y.id for b in league_scoped_badges)


# ---------------------------------------------------------------------------
# Personal (league_id IS NULL) badges from a finished/other competition must
# not leak into a live leaderboard just because they're still is_active and
# league_id IS NULL matches the "personal badge" branch of the OR filter.
# ---------------------------------------------------------------------------

def test_leaderboard_does_not_leak_personal_badge_from_other_competition(db_session):
    old_comp = _make_competition(db_session, "WC2026")
    new_comp = _make_competition(db_session, "Champions League")
    user = _make_user(db_session, "player")

    new_league = League(name="CL League", competition_id=new_comp.id)
    db_session.add(new_league)
    db_session.flush()
    db_session.add(UserLeague(user_id=user.id, league_id=new_league.id))

    # A personal badge (league_id NULL) awarded back in the OLD competition —
    # still is_active because nothing ever swept it after the tournament ended.
    db_session.add(UserBadge(
        user_id=user.id, badge_code="joker_master",
        league_id=None, competition_id=old_comp.id, is_active=True,
    ))
    db_session.commit()

    leaderboard = ranking_service.get_leaderboard(db_session, new_league.id)

    entry = next(e for e in leaderboard if e["user_id"] == user.id)
    assert entry["badges"] == []
