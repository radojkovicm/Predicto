from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.orm import Session

from app.auth.flash import flash, get_flashes
from app.auth.password import hash_password
from app.db import get_db
from app.models.models import League, User, UserLeague

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")
limiter = Limiter(key_func=get_remote_address)


@router.get("/join/{code}")
async def join_get(code: str, request: Request, db: Session = Depends(get_db)):
    league = db.query(League).filter(League.join_code == code).first()
    if not league:
        flash(request, "This invite link is invalid or has been revoked.", "error")
        return RedirectResponse("/login", status_code=302)
    return templates.TemplateResponse(
        "join.html",
        {"request": request, "flashes": get_flashes(request), "league": league, "code": code},
    )


@router.post("/join/{code}")
@limiter.limit("10/minute")
async def join_post(code: str, request: Request, db: Session = Depends(get_db)):
    league = db.query(League).filter(League.join_code == code).first()
    if not league:
        flash(request, "This invite link is invalid or has been revoked.", "error")
        return RedirectResponse("/login", status_code=302)

    form = await request.form()
    username = str(form.get("username", "")).strip()
    password = str(form.get("password", ""))
    first_name = str(form.get("first_name", "")).strip() or None
    last_name = str(form.get("last_name", "")).strip() or None

    if not username or len(password) < 6:
        flash(request, "Username required and password must be ≥ 6 characters.", "error")
        return RedirectResponse(f"/join/{code}", status_code=302)

    if db.query(User).filter(User.username == username).first():
        flash(request, f"Username '{username}' is already taken.", "error")
        return RedirectResponse(f"/join/{code}", status_code=302)

    user = User(
        username=username,
        password_hash=hash_password(password),
        first_name=first_name,
        last_name=last_name,
        is_approved=False,
    )
    db.add(user)
    db.flush()
    db.add(UserLeague(user_id=user.id, league_id=league.id))
    db.commit()

    flash(
        request,
        f"Thanks! Your request to join '{league.name}' was sent to the admin for approval. "
        "You'll be able to log in once it's approved.",
        "success",
    )
    return RedirectResponse("/login", status_code=302)
