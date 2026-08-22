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

    # Scoring rules are per-competition (see scoring_service.ScoringConfig) — fall back
    # to its defaults (WC2026's original hardcoded values) if no competition exists yet.
    points_outcome = competition.points_outcome if competition else 10
    points_goal_diff = competition.points_goal_diff if competition else 7
    points_goal_home = competition.points_goal_home if competition else 4
    points_goal_away = competition.points_goal_away if competition else 4
    joker_bonus = competition.joker_bonus if competition else 8
    joker_penalty = competition.joker_penalty if competition else -5
    max_base = points_outcome + points_goal_diff + points_goal_home + points_goal_away

    # Only show the phase-multiplier section when it's actually in use — most
    # competitions leave every phase at the neutral 1.00 and this would just be noise.
    phases = sorted(competition.phases, key=lambda p: p.order_index) if competition else []
    has_multiplier = any(p.point_multiplier != 1 for p in phases)

    return templates.TemplateResponse(
        "info.html",
        {
            "request": request,
            "current_user": current_user,
            "flashes": get_flashes(request),
            "jokers_per_phase": jokers_per_phase,
            "phase_count": phase_count,
            "points_outcome": points_outcome,
            "points_goal_diff": points_goal_diff,
            "points_goal_home": points_goal_home,
            "points_goal_away": points_goal_away,
            "joker_bonus": joker_bonus,
            "joker_penalty": joker_penalty,
            "max_base": max_base,
            "max_with_joker": max_base + joker_bonus,
            "phases": phases,
            "has_multiplier": has_multiplier,
        },
    )
