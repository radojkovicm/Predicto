import pytz
from datetime import datetime, timezone
from datetime import timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session, joinedload

from app.auth.csrf import csrf_token
from app.auth.deps import require_login
from app.auth.flash import get_flashes
from app.db import get_db
from app.models.models import Competition, Match, Phase, Prediction, User
from app.services import lock_service, stats_service
from app.services.league_service import resolve_league

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")
templates.env.globals["csrf_token"] = csrf_token
TZ_DISPLAY = pytz.timezone("Europe/Ljubljana")


def _to_local(dt: datetime) -> datetime:
    if dt is None:
        return dt
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(TZ_DISPLAY)


@router.get("/")
async def index(request: Request):
    return RedirectResponse("/matches", status_code=302)


@router.get("/matches")
async def match_list(
    request: Request,
    phase_id: Optional[int] = None,
    current_user: User = Depends(require_login),
    db: Session = Depends(get_db),
):
    # Only the single active competition is predictable day-to-day — finished
    # competitions (e.g. a past World Cup) belong in the admin archive, not here.
    active_competition = db.query(Competition).filter(Competition.status == "active").first()
    if not active_competition:
        phases = []
        matches_query = db.query(Match).filter(False)
    else:
        phases = (
            db.query(Phase)
            .filter(Phase.competition_id == active_competition.id)
            .order_by(Phase.order_index)
            .all()
        )
        matches_query = (
            db.query(Match)
            .options(joinedload(Match.phase))
            .filter(Match.competition_id == active_competition.id)
            .order_by(Match.kickoff_utc)
        )
    if phase_id:
        # Phase tab: show ALL matches in that phase (full history + upcoming)
        matches_query = matches_query.filter(Match.phase_id == phase_id)
    elif active_competition:
        # "All" tab: admin must have marked it visible AND
        # it's either not finished yet OR finished within the 12h grace period.
        # Admin can still force-hide by toggling is_visible=False (takes effect immediately).
        from sqlalchemy import and_, or_
        grace_cutoff = datetime.now(timezone.utc) - timedelta(hours=12)
        matches_query = matches_query.filter(
            Match.is_visible == True,
            or_(
                Match.is_finished == False,
                Match.finished_at > grace_cutoff,
            )
        )
    matches = matches_query.all()

    user_preds: dict[int, Prediction] = {}
    if matches:
        match_ids = [m.id for m in matches]
        preds = db.query(Prediction).filter(
            Prediction.user_id == current_user.id,
            Prediction.match_id.in_(match_ids),
        ).all()
        user_preds = {p.match_id: p for p in preds}

    from collections import defaultdict
    grouped: dict[int, list] = defaultdict(list)
    phase_map: dict[int, Phase] = {}
    for match in matches:
        grouped[match.phase_id].append(match)
        phase_map[match.phase_id] = match.phase

    grouped_phases = [
        {"phase": phase_map[pid], "matches": grouped[pid]}
        for pid in sorted(grouped.keys(), key=lambda pid: phase_map[pid].order_index)
    ]

    return templates.TemplateResponse(
        "matches.html",
        {
            "request": request,
            "current_user": current_user,
            "flashes": get_flashes(request),
            "phases": phases,
            "grouped_phases": grouped_phases,
            "user_preds": user_preds,
            "is_locked": lock_service.is_locked,
            "to_local": _to_local,
            "selected_phase_id": phase_id,
        },
    )


@router.get("/matches/{match_id}")
async def match_detail(
    match_id: int,
    request: Request,
    league_id: Optional[int] = None,
    current_user: User = Depends(require_login),
    db: Session = Depends(get_db),
):
    match = (
        db.query(Match)
        .options(joinedload(Match.phase))
        .filter(Match.id == match_id)
        .first()
    )
    if not match or match.competition.status != "active":
        # Non-active (draft/finished) competitions are only browsable via the
        # admin archive — a direct/bookmarked link must not leak them.
        return RedirectResponse("/matches", status_code=302)

    locked = lock_service.is_locked(match)
    # Treat hidden matches as locked for prediction purposes
    if not match.is_visible:
        locked = True

    user_pred = db.query(Prediction).filter(
        Prediction.user_id == current_user.id,
        Prediction.match_id == match_id,
    ).first()

    jokers_used_in_phase_query = (
        db.query(Prediction)
        .join(Match, Prediction.match_id == Match.id)
        .filter(
            Prediction.user_id == current_user.id,
            Match.phase_id == match.phase_id,
            Prediction.is_joker == True,
        )
    )
    if user_pred is not None:
        jokers_used_in_phase_query = jokers_used_in_phase_query.filter(Prediction.id != user_pred.id)
    jokers_used_in_phase = jokers_used_in_phase_query.count()

    can_use_joker = match.phase.joker_allowed and (
        jokers_used_in_phase < match.competition.jokers_per_phase
    )

    # Resolve league context for stats
    active_league, user_leagues = resolve_league(db, current_user.id, league_id)
    stats = {}
    if locked:
        stats = stats_service.get_match_stats(
            db, match_id,
            league_id=active_league.id if active_league else None,
        )

    return templates.TemplateResponse(
        "match_detail.html",
        {
            "request": request,
            "current_user": current_user,
            "flashes": get_flashes(request),
            "match": match,
            "locked": locked,
            "user_pred": user_pred,
            "can_use_joker": can_use_joker,
            "stats": stats,
            "to_local": _to_local,
            "active_league": active_league,
            "user_leagues": user_leagues,
        },
    )
