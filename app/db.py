import os
import shutil

from sqlalchemy import create_engine
from sqlalchemy.exc import ArgumentError
from sqlalchemy.orm import sessionmaker, Session
from typing import Generator
from config.config import settings

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
