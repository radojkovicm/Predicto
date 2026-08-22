from fastapi import APIRouter, Depends, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from typing import Optional

from app.auth.csrf import csrf_token
from app.auth.deps import require_login
from app.auth.flash import get_flashes
from app.db import get_db
from app.models.models import User
from app.services import ranking_service
from app.services.badge_service import badge_display
from app.services.league_service import resolve_league

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")
templates.env.globals["csrf_token"] = csrf_token


@router.get("/ranking")
async def ranking(
    request: Request,
    league_id: Optional[int] = None,
    current_user: User = Depends(require_login),
    db: Session = Depends(get_db),
):
    active_league, user_leagues = resolve_league(db, current_user.id, league_id)

    leaderboard = []
    if active_league:
        leaderboard = ranking_service.get_leaderboard(db, active_league.id)

    return templates.TemplateResponse(
        "ranking.html",
        {
            "request": request,
            "current_user": current_user,
            "flashes": get_flashes(request),
            "leaderboard": leaderboard,
            "active_league": active_league,
            "user_leagues": user_leagues,
            "badge_display": badge_display,
        },
    )
