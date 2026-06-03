from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.orm import Session

from app.auth.flash import flash, get_flashes
from app.auth.password import verify_password
from app.db import get_db
from app.models.models import User

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")
limiter = Limiter(key_func=get_remote_address)

LOCKOUT_ATTEMPTS = 10
LOCKOUT_MINUTES = 30


@router.get("/login")
async def login_get(request: Request):
    flashes = get_flashes(request)
    return templates.TemplateResponse("login.html", {"request": request, "flashes": flashes})


@router.post("/login")
@limiter.limit("10/minute")  # IP-level: max 10 requests/min per IP
async def login_post(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    username = str(form.get("username", "")).strip()
    password = str(form.get("password", ""))

    user = db.query(User).filter(User.username == username).first()

    # Account lockout check
    if user and user.locked_until:
        now = datetime.now(timezone.utc)
        locked_until = user.locked_until
        if locked_until.tzinfo is None:
            locked_until = locked_until.replace(tzinfo=timezone.utc)
        if locked_until > now:
            remaining = max(1, int((locked_until - now).total_seconds() / 60))
            flash(
                request,
                f"Account locked due to too many failed attempts. Try again in {remaining} minute(s).",
                "error",
            )
            return RedirectResponse("/login", status_code=302)
        # Lock expired — reset
        user.failed_login_attempts = 0
        user.locked_until = None
        db.commit()

    if not user or not verify_password(password, user.password_hash):
        if user:
            user.failed_login_attempts = (user.failed_login_attempts or 0) + 1
            if user.failed_login_attempts >= LOCKOUT_ATTEMPTS:
                user.locked_until = datetime.now(timezone.utc) + timedelta(minutes=LOCKOUT_MINUTES)
                db.commit()
                flash(
                    request,
                    f"Account locked for {LOCKOUT_MINUTES} minutes after too many failed attempts.",
                    "error",
                )
                return RedirectResponse("/login", status_code=302)
            db.commit()
        flash(request, "Invalid username or password.", "error")
        return RedirectResponse("/login", status_code=302)

    # Successful login
    user.failed_login_attempts = 0
    user.locked_until = None
    db.commit()

    request.session["user_id"] = user.id
    return RedirectResponse("/", status_code=302)


@router.post("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=302)
