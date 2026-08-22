"""HTTP-level coverage for the two newest security-sensitive surfaces:
  - CSRF: every mutating route is now guarded by a router-level dependency
    (app/auth/csrf.py) instead of per-route wiring, so this exercises the
    actual FastAPI app rather than the check function in isolation.
  - Invite links: a public /join/{code} registration route now creates
    unapproved accounts that must be blocked from logging in until an admin
    approves them.

Uses a real (in-memory sqlite) app instance via TestClient, with get_db
overridden — everything else (sessions, CSRF, routing) runs for real.
"""
import re

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth.password import hash_password
from app.db import get_db
from app.main import app
from app.models.models import Base, Competition, League


def _extract_csrf_token(html: str) -> str:
    match = re.search(r'name="csrf-token" content="([^"]+)"', html)
    assert match, "csrf-token meta tag not found in response"
    return match.group(1)


@pytest.fixture()
def app_client():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine)

    def override_get_db():
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    yield TestSession
    app.dependency_overrides.clear()
    engine.dispose()


def _make_admin(TestSession, username="admin", password="adminpass123"):
    from app.models.models import User
    db = TestSession()
    user = User(username=username, password_hash=hash_password(password), is_admin=True, is_approved=True)
    db.add(user)
    db.commit()
    db.close()


def _make_league_with_invite(TestSession, code="TESTCODE123"):
    db = TestSession()
    competition = Competition(name="Test Cup", status="active")
    db.add(competition)
    db.flush()
    league = League(name="Test League", competition_id=competition.id, join_code=code)
    db.add(league)
    db.commit()
    db.close()


# ---------------------------------------------------------------------------
# CSRF
# ---------------------------------------------------------------------------

def test_post_without_csrf_token_is_rejected(app_client):
    with TestClient(app) as client:
        resp = client.post("/login", data={"username": "nobody", "password": "wrong"})
    assert resp.status_code == 403


def test_post_with_wrong_csrf_token_is_rejected(app_client):
    with TestClient(app) as client:
        client.get("/login")
        resp = client.post(
            "/login",
            data={"username": "nobody", "password": "wrong", "csrf_token": "not-the-real-token"},
        )
    assert resp.status_code == 403


def test_post_with_correct_csrf_token_reaches_the_route(app_client):
    with TestClient(app) as client:
        get_resp = client.get("/login")
        token = _extract_csrf_token(get_resp.text)
        resp = client.post(
            "/login",
            data={"username": "nobody", "password": "wrong", "csrf_token": token},
            follow_redirects=False,
        )
    # Wrong credentials, but past the CSRF gate — a normal redirect back to
    # /login with a flash, not a 403.
    assert resp.status_code == 302
    assert resp.headers["location"] == "/login"


# ---------------------------------------------------------------------------
# Invite link -> pending approval -> login gate
# ---------------------------------------------------------------------------

def test_invite_signup_is_blocked_until_admin_approves(app_client):
    TestSession = app_client
    _make_admin(TestSession, username="admin", password="adminpass123")
    _make_league_with_invite(TestSession, code="TESTCODE123")

    with TestClient(app) as newuser_client:
        get_resp = newuser_client.get("/join/TESTCODE123")
        assert get_resp.status_code == 200
        token = _extract_csrf_token(get_resp.text)

        signup_resp = newuser_client.post(
            "/join/TESTCODE123",
            data={"username": "newplayer", "password": "playerpass1", "csrf_token": token},
            follow_redirects=False,
        )
        assert signup_resp.status_code == 302

        # Not approved yet — login must be refused.
        login_page = newuser_client.get("/login")
        login_token = _extract_csrf_token(login_page.text)
        blocked_resp = newuser_client.post(
            "/login",
            data={"username": "newplayer", "password": "playerpass1", "csrf_token": login_token},
            follow_redirects=False,
        )
        assert blocked_resp.status_code == 302
        assert blocked_resp.headers["location"] == "/login"
        assert newuser_client.cookies.get("predicto_session") is None or "user_id" not in str(
            newuser_client.cookies
        )

    # Admin approves.
    with TestClient(app) as admin_client:
        admin_login_page = admin_client.get("/login")
        admin_token = _extract_csrf_token(admin_login_page.text)
        admin_client.post(
            "/login",
            data={"username": "admin", "password": "adminpass123", "csrf_token": admin_token},
            follow_redirects=False,
        )

        users_page = admin_client.get("/admin/users")
        assert "newplayer" in users_page.text

        db = TestSession()
        from app.models.models import User
        pending = db.query(User).filter(User.username == "newplayer").first()
        approve_page_token = _extract_csrf_token(users_page.text)
        db.close()

        approve_resp = admin_client.post(
            f"/admin/users/{pending.id}/approve",
            data={"csrf_token": approve_page_token},
            follow_redirects=False,
        )
        assert approve_resp.status_code == 302

    # Now the new user can log in.
    with TestClient(app) as newuser_client2:
        login_page = newuser_client2.get("/login")
        token = _extract_csrf_token(login_page.text)
        resp = newuser_client2.post(
            "/login",
            data={"username": "newplayer", "password": "playerpass1", "csrf_token": token},
            follow_redirects=False,
        )
        assert resp.status_code == 302
        assert resp.headers["location"] == "/"
