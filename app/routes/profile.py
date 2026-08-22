import pytz
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session, joinedload

from app.auth.deps import require_login
from app.auth.flash import get_flashes
from app.db import get_db
from app.models.models import Match, Prediction, User, UserBadge
from app.services.badge_service import badge_display
from app.services.league_service import resolve_league

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")
TZ_DISPLAY = pytz.timezone("Europe/Ljubljana")


def _to_local(dt: datetime) -> datetime:
    if dt is None:
        return dt
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(TZ_DISPLAY)


@router.get("/profile")
async def my_profile(request: Request, current_user: User = Depends(require_login)):
    return RedirectResponse(f"/profile/{current_user.id}", status_code=302)


@router.get("/profile/{user_id}")
async def user_profile(
    user_id: int,
    request: Request,
    league_id: Optional[int] = None,
    current_user: User = Depends(require_login),
    db: Session = Depends(get_db),
):
    profile_user = db.query(User).filter(User.id == user_id).first()
    if not profile_user:
        return RedirectResponse("/ranking", status_code=302)

    # League context — use viewer's leagues for the tab switcher
    active_league, user_leagues = resolve_league(db, current_user.id, league_id)

    # No active_league means the viewer has no live competition context (e.g. right
    # after a competition finished and before the next one starts) — show nothing
    # rather than falling back to unscoped history from a finished competition.
    predictions = []
    badges = []
    if active_league:
        predictions = (
            db.query(Prediction)
            .options(joinedload(Prediction.match).joinedload(Match.phase))
            .filter(Prediction.user_id == user_id)
            .join(Match)
            .filter(Match.competition_id == active_league.competition_id)
            .order_by(Match.kickoff_utc.desc())
            .all()
        )

        from sqlalchemy import or_
        badges = (
            db.query(UserBadge)
            .options(joinedload(UserBadge.match), joinedload(UserBadge.league))
            .filter(
                UserBadge.user_id == user_id,
                UserBadge.is_active == True,
                or_(UserBadge.league_id == active_league.id, UserBadge.league_id == None),
            )
            .order_by(UserBadge.awarded_at.desc())
            .all()
        )

    total_points = sum(p.points for p in predictions if p.points is not None)

    return templates.TemplateResponse(
        "profile.html",
        {
            "request": request,
            "current_user": current_user,
            "flashes": get_flashes(request),
            "profile_user": profile_user,
            "predictions": predictions,
            "badges": badges,
            "total_points": total_points,
            "active_league": active_league,
            "user_leagues": user_leagues,
            "badge_display": badge_display,
            "to_local": _to_local,
        },
    )
