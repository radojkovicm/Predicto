"""Helpers for resolving league context in routes."""
from typing import Optional
from sqlalchemy.orm import Session

from app.models.models import League, UserLeague


def get_user_leagues(db: Session, user_id: int) -> list[League]:
    return (
        db.query(League)
        .join(UserLeague, League.id == UserLeague.league_id)
        .filter(UserLeague.user_id == user_id)
        .order_by(League.name)
        .all()
    )


def resolve_league(
    db: Session,
    user_id: int,
    requested_league_id: Optional[int],
) -> tuple[Optional[League], list[League]]:
    """Returns (active_league, all_user_leagues).
    active_league is None if user has no leagues.
    """
    leagues = get_user_leagues(db, user_id)
    if not leagues:
        return None, []
    if requested_league_id:
        active = next((l for l in leagues if l.id == requested_league_id), leagues[0])
    else:
        active = leagues[0]
    return active, leagues
