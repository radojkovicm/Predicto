import os
import shutil
import sqlite3
from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.exc import ArgumentError
from sqlalchemy.orm import sessionmaker, Session
from typing import Generator
from config.config import settings

# app/demo_seed.db ships a small Group Stage — mostly finished (recently
# played), plus a few still open — and its kickoff times get re-anchored to
# real "now" every cold start (see below) so the live Vercel demo always
# looks current instead of the fixed dates baked in when the seed was
# generated slowly drifting away. Finished matches are spread `per_day`
# per day, ending TODAY for the most recent one; open matches start a
# couple of days out, so there's always something to actually predict.
def _reanchor_demo_dates(db_path: str, per_day: int = 4) -> None:
    now = datetime.now(timezone.utc)
    conn = sqlite3.connect(db_path)
    try:
        finished = conn.execute(
            "SELECT id FROM matches WHERE is_finished = 1 ORDER BY id"
        ).fetchall()
        n = len(finished)
        for idx, (match_id,) in enumerate(finished):
            days_ago = (n - 1 - idx) // per_day  # most recent (last idx) -> 0 = today
            hour = 14 + (idx % per_day) * 3
            kickoff = (now - timedelta(days=days_ago)).replace(
                hour=hour % 24, minute=0, second=0, microsecond=0
            )
            finished_at = kickoff + timedelta(hours=2)
            conn.execute(
                "UPDATE matches SET kickoff_utc = ?, finished_at = ? WHERE id = ?",
                (kickoff.isoformat(), finished_at.isoformat(), match_id),
            )

        open_matches = conn.execute(
            "SELECT id FROM matches WHERE is_finished = 0 ORDER BY id"
        ).fetchall()
        for idx, (match_id,) in enumerate(open_matches):
            days_ahead = idx + 2  # first open match is always ~2 days out
            hour = 12 + (idx % 4) * 3
            kickoff = (now + timedelta(days=days_ahead)).replace(
                hour=hour % 24, minute=0, second=0, microsecond=0
            )
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
