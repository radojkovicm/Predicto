"""Covers what's new/risky from hiding finished competitions from live users:
  - get_user_leagues drops leagues whose competition is finished (the fix that
    stops WC2026 history leaking into /profile, /ranking once no league is active).
  - save_prediction only accepts predictions for an ACTIVE competition (closes
    the draft-competition gap alongside the already-existing finished check).
"""
from datetime import datetime, timezone

import pytest

from app.models.models import Competition, League, Match, Phase, User, UserLeague
from app.services import league_service, prediction_service

FUTURE_KICKOFF = datetime(2030, 1, 1, tzinfo=timezone.utc)


def _make_competition(db, name, status):
    competition = Competition(name=name, status=status)
    db.add(competition)
    db.flush()
    return competition


def _make_user(db, username):
    user = User(username=username, password_hash="x")
    db.add(user)
    db.flush()
    return user


def _make_league(db, name, competition_id):
    league = League(name=name, competition_id=competition_id)
    db.add(league)
    db.flush()
    return league


def _make_match(db, competition_id, is_visible=True):
    phase = Phase(name="Final", order_index=1, competition_id=competition_id)
    db.add(phase)
    db.flush()
    match = Match(
        phase_id=phase.id,
        team1_code="AAA", team1_name="Team A",
        team2_code="BBB", team2_name="Team B",
        kickoff_utc=FUTURE_KICKOFF,
        is_visible=is_visible,
        competition_id=competition_id,
    )
    db.add(match)
    db.flush()
    return match


def test_get_user_leagues_excludes_finished_competition(db_session):
    finished = _make_competition(db_session, "WC2026", "finished")
    active = _make_competition(db_session, "Champions League", "active")
    user = _make_user(db_session, "player")

    old_league = _make_league(db_session, "Old League", finished.id)
    new_league = _make_league(db_session, "New League", active.id)
    db_session.add_all([
        UserLeague(user_id=user.id, league_id=old_league.id),
        UserLeague(user_id=user.id, league_id=new_league.id),
    ])
    db_session.commit()

    leagues = league_service.get_user_leagues(db_session, user.id)

    assert [l.id for l in leagues] == [new_league.id]


def test_get_user_leagues_excludes_archived_league_even_if_competition_active(db_session):
    """A single league can retire early without the whole competition (or its
    other leagues) being touched — that's the point of archived_at vs. the
    competition-level finished status above.
    """
    from datetime import datetime, timezone as tz

    active = _make_competition(db_session, "Champions League", "active")
    user = _make_user(db_session, "player")

    archived_league = _make_league(db_session, "Retired Group", active.id)
    archived_league.archived_at = datetime.now(tz.utc)
    live_league = _make_league(db_session, "Still Playing", active.id)
    db_session.add_all([
        UserLeague(user_id=user.id, league_id=archived_league.id),
        UserLeague(user_id=user.id, league_id=live_league.id),
    ])
    db_session.commit()

    leagues = league_service.get_user_leagues(db_session, user.id)

    assert [l.id for l in leagues] == [live_league.id]


def test_get_user_leagues_empty_when_only_league_is_finished(db_session):
    finished = _make_competition(db_session, "WC2026", "finished")
    user = _make_user(db_session, "player")
    old_league = _make_league(db_session, "Old League", finished.id)
    db_session.add(UserLeague(user_id=user.id, league_id=old_league.id))
    db_session.commit()

    assert league_service.get_user_leagues(db_session, user.id) == []


@pytest.mark.parametrize("status", ["draft", "finished"])
def test_save_prediction_rejects_non_active_competition(db_session, status):
    competition = _make_competition(db_session, "Not Live", status)
    user = _make_user(db_session, "player")
    match = _make_match(db_session, competition.id)
    db_session.commit()

    with pytest.raises(ValueError, match="isn't open for predictions"):
        prediction_service.save_prediction(db_session, user, match, 1, 0, is_joker=False)


def test_save_prediction_allows_active_competition(db_session):
    competition = _make_competition(db_session, "Live One", "active")
    user = _make_user(db_session, "player")
    match = _make_match(db_session, competition.id)
    db_session.commit()

    pred = prediction_service.save_prediction(db_session, user, match, 1, 0, is_joker=False)

    assert pred.pred_goals1 == 1 and pred.pred_goals2 == 0
