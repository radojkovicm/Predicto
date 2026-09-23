import os
import shutil
import sqlite3
from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.exc import ArgumentError
from sqlalchemy.orm import sessionmaker, Session
from typing import Generator
from config.config import settings

# Demo-only match IDs in app/demo_seed.db, with their kickoff re-anchored to
# the real "now" every cold start (see _reanchor_demo_dates below) so the
# live Vercel demo always has a few matches genuinely open for prediction,
# a couple days out, instead of the fixed dates baked in when the seed was
# generated slowly drifting into the past.
_DEMO_FINISHED_DAYS_AGO = {1: 10, 2: 9, 3: 8, 7: 7, 8: 6, 4: 5, 5: 4, 6: 3, 9: 2, 11: 1}
_DEMO_OPEN_DAYS_AHEAD = {10: 2, 12: 2, 15: 4, 14: 5}


def _reanchor_demo_dates(db_path: str) -> None:
    now = datetime.now(timezone.utc)
    conn = sqlite3.connect(db_path)
    try:
        for match_id, days_ago in _DEMO_FINISHED_DAYS_AGO.items():
            kickoff = now - timedelta(days=days_ago, hours=match_id % 5)
            finished_at = kickoff + timedelta(hours=2)
            conn.execute(
                "UPDATE matches SET kickoff_utc = ?, finished_at = ? WHERE id = ?",
                (kickoff.isoformat(), finished_at.isoformat(), match_id),
            )
        for match_id, days_ahead in _DEMO_OPEN_DAYS_AHEAD.items():
            kickoff = now + timedelta(days=days_ahead, hours=match_id % 5)
            conn.execute(
                "UPDATE matches SET kickoff_utc = ? WHERE id = ?",
                (kickoff.isoformat(), match_id),
            )
        conn.commit()
    finally:
        conn.close()


# Vercel demo mode: sqlite:////tmp/<name>.db points at the function's
# writable /tmp, which starts empty on every cold start. Seed it from the
# read-only bundled demo_seed.db so the live demo always has something to
# show, without needing a real Postgres database.
if settings.DATABASE_URL.startswith("sqlite:////tmp/"):
    _tmp_path = settings.DATABASE_URL.removeprefix("sqlite:///")
    if not os.path.exists(_tmp_path):
        _seed_path = os.path.join(os.path.dirname(__file__), "demo_seed.db")
        if os.path.exists(_seed_path):
            shutil.copyfile(_seed_path, _tmp_path)
            _reanchor_demo_dates(_tmp_path)

_is_sqlite = settings.DATABASE_URL.startswith("sqlite")
_connect_args = {"check_same_thread": False} if _is_sqlite else {}
try:
    engine = create_engine(
        settings.DATABASE_URL,
        connect_args=_connect_args,
        pool_pre_ping=not _is_sqlite,
    )
except ArgumentError as exc:
    # Never log the raw value (it contains the DB password) — just enough
    # shape info to diagnose a bad env var without leaking the secret.
    url = settings.DATABASE_URL
    raise ArgumentError(
        f"DATABASE_URL is not a valid SQLAlchemy URL (len={len(url)}, "
        f"has_scheme_sep={'://' in url}, has_newline={chr(10) in url!r}, "
        f"starts_with={url[:12]!r}...). Check the env var for stray quotes, "
        f"whitespace, or a missing scheme."
    ) from exc
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
