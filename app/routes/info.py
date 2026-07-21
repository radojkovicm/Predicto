from fastapi import APIRouter, Depends, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.auth.deps import require_login
from app.auth.flash import get_flashes
from app.db import get_db
from app.models.models import Competition, User

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/info")
async def info(
    request: Request,
    current_user: User = Depends(require_login),
    db: Session = Depends(get_db),
):
    # No competition is guaranteed to be "active" (e.g. right after WC2026 finished
    # and before the next one starts). Prefer active, then the most recent finished
    # one (real, complete rules) — never a draft, which may be half-configured.
    competition = (
        db.query(Competition).filter(Competition.status == "active").first()
        or db.query(Competition)
        .filter(Competition.status == "finished")
        .order_by(Competition.id.desc())
        .first()
    )
    jokers_per_phase = competition.jokers_per_phase if competition else None
    phase_count = len(competition.phases) if competition else None

    return templates.TemplateResponse(
        "info.html",
        {
            "request": request,
            "current_user": current_user,
            "flashes": get_flashes(request),
            "jokers_per_phase": jokers_per_phase,
            "phase_count": phase_count,
        },
    )
