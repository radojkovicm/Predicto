from datetime import datetime, timedelta, timezone
from app.models.models import Match

LOCK_MINUTES = 15


def lock_threshold(match: Match) -> datetime:
    """Returns the UTC cutoff time — predictions are locked after this."""
    kt = match.kickoff_utc
    if kt.tzinfo is None:
        kt = kt.replace(tzinfo=timezone.utc)
    return kt - timedelta(minutes=LOCK_MINUTES)


def is_locked(match: Match) -> bool:
    """True if the prediction window for this match is closed.
    Locked when: result already entered OR within 15 min of kickoff.
    """
    if match.is_finished:
        return True
    return datetime.now(timezone.utc) >= lock_threshold(match)
