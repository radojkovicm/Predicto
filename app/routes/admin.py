import pytz
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session, joinedload

from app.auth.deps import require_admin
from app.auth.flash import flash, get_flashes
from app.auth.password import hash_password
from app.db import get_db
from app.models.models import League, Match, Phase, Prediction, PredictionLog, ResultLog, User, UserLeague
from app.services import result_service

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")
TZ_DISPLAY = pytz.timezone("Europe/Ljubljana")


def _to_local(dt: datetime) -> datetime:
    if dt is None:
        return dt
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(TZ_DISPLAY)


def _parse_kickoff(value: str) -> datetime:
    """Parse a datetime-local HTML input (naive) as UTC."""
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------

@router.get("/users")
async def users_list(
    request: Request,
    admin_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    users = db.query(User).order_by(User.username).all()
    leagues = db.query(League).order_by(League.name).all()
    # Build user→leagues map
    user_league_map: dict[int, list[int]] = {}
    for ul in db.query(UserLeague).all():
        user_league_map.setdefault(ul.user_id, []).append(ul.league_id)

    return templates.TemplateResponse(
        "admin/users.html",
        {
            "request": request,
            "current_user": admin_user,
            "flashes": get_flashes(request),
            "users": users,
            "leagues": leagues,
            "user_league_map": user_league_map,
            "to_local": _to_local,
        },
    )


@router.post("/users")
async def create_user(
    request: Request,
    admin_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    form = await request.form()
    username = str(form.get("username", "")).strip()
    password = str(form.get("password", ""))
    first_name = str(form.get("first_name", "")).strip() or None
    last_name = str(form.get("last_name", "")).strip() or None
    is_admin = form.get("is_admin") == "1"

    if not username or len(password) < 6:
        flash(request, "Username required and password must be ≥ 6 characters.", "error")
        return RedirectResponse("/admin/users", status_code=302)

    existing = db.query(User).filter(User.username == username).first()
    if existing:
        flash(request, f"Username '{username}' already exists.", "error")
        return RedirectResponse("/admin/users", status_code=302)

    user = User(
        username=username,
        password_hash=hash_password(password),
        first_name=first_name,
        last_name=last_name,
        is_admin=is_admin,
    )
    db.add(user)
    db.flush()

    # Assign to leagues (multi-select sends multiple league_ids values)
    for key, val in form.multi_items():
        if key == "league_ids":
            league = db.query(League).filter(League.id == int(val)).first()
            if league:
                db.add(UserLeague(user_id=user.id, league_id=league.id))

    db.commit()
    flash(request, f"User '{username}' created.", "success")
    return RedirectResponse("/admin/users", status_code=302)


@router.get("/users/{user_id}/edit")
async def edit_user_form(
    user_id: int,
    request: Request,
    admin_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        flash(request, "User not found.", "error")
        return RedirectResponse("/admin/users", status_code=302)
    return templates.TemplateResponse(
        "admin/user_edit.html",
        {
            "request": request,
            "current_user": admin_user,
            "flashes": get_flashes(request),
            "user": user,
        },
    )


@router.post("/users/{user_id}/edit")
async def edit_user(
    user_id: int,
    request: Request,
    admin_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        flash(request, "User not found.", "error")
        return RedirectResponse("/admin/users", status_code=302)

    form = await request.form()
    new_username = str(form.get("username", "")).strip()
    first_name = str(form.get("first_name", "")).strip() or None
    last_name = str(form.get("last_name", "")).strip() or None
    is_admin = form.get("is_admin") == "1"

    if not new_username:
        flash(request, "Username cannot be empty.", "error")
        return RedirectResponse(f"/admin/users/{user_id}/edit", status_code=302)

    # Check username uniqueness (only if changed)
    if new_username != user.username:
        conflict = db.query(User).filter(User.username == new_username).first()
        if conflict:
            flash(request, f"Username '{new_username}' is already taken.", "error")
            return RedirectResponse(f"/admin/users/{user_id}/edit", status_code=302)

    # Prevent admin from accidentally removing their own admin status
    if user_id == admin_user.id and not is_admin:
        flash(request, "You cannot remove admin status from your own account.", "error")
        return RedirectResponse(f"/admin/users/{user_id}/edit", status_code=302)

    user.username = new_username
    user.first_name = first_name
    user.last_name = last_name
    user.is_admin = is_admin
    db.commit()
    flash(request, f"User '{new_username}' updated.", "success")
    return RedirectResponse("/admin/users", status_code=302)


@router.post("/users/{user_id}/reset-password")
async def reset_password(
    user_id: int,
    request: Request,
    admin_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    form = await request.form()
    new_password = str(form.get("new_password", ""))
    if len(new_password) < 6:
        flash(request, "Password must be ≥ 6 characters.", "error")
        return RedirectResponse("/admin/users", status_code=302)

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        flash(request, "User not found.", "error")
        return RedirectResponse("/admin/users", status_code=302)

    user.password_hash = hash_password(new_password)
    user.failed_login_attempts = 0
    user.locked_until = None
    db.commit()
    flash(request, f"Password reset for '{user.username}'.", "success")
    return RedirectResponse("/admin/users", status_code=302)


@router.post("/users/{user_id}/unlock")
async def unlock_user(
    user_id: int,
    request: Request,
    admin_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.id == user_id).first()
    if user:
        user.failed_login_attempts = 0
        user.locked_until = None
        db.commit()
        flash(request, f"Account '{user.username}' unlocked.", "success")
    return RedirectResponse("/admin/users", status_code=302)


@router.post("/users/{user_id}/delete")
async def delete_user(
    user_id: int,
    request: Request,
    admin_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        flash(request, "User not found.", "error")
        return RedirectResponse("/admin/users", status_code=302)

    username = user.username
    db.query(PredictionLog).filter(PredictionLog.user_id == user_id).delete()
    db.query(Prediction).filter(Prediction.user_id == user_id).delete()
    from app.models.models import UserBadge
    db.query(UserBadge).filter(UserBadge.user_id == user_id).delete()
    db.query(UserLeague).filter(UserLeague.user_id == user_id).delete()
    db.delete(user)
    db.commit()
    flash(request, f"User '{username}' deleted completely.", "success")
    return RedirectResponse("/admin/users", status_code=302)


# ---------------------------------------------------------------------------
# Matches
# ---------------------------------------------------------------------------

@router.get("/matches")
async def matches_list(
    request: Request,
    admin_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    matches = (
        db.query(Match)
        .options(joinedload(Match.phase))
        .order_by(Match.kickoff_utc)
        .all()
    )
    phases = db.query(Phase).order_by(Phase.order_index).all()
    visible_count = sum(1 for m in matches if m.is_visible)
    return templates.TemplateResponse(
        "admin/matches.html",
        {
            "request": request,
            "current_user": admin_user,
            "flashes": get_flashes(request),
            "matches": matches,
            "phases": phases,
            "visible_count": visible_count,
            "to_local": _to_local,
        },
    )


@router.post("/matches/{match_id}/toggle-visibility")
async def toggle_visibility(
    match_id: int,
    request: Request,
    admin_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    match = db.query(Match).filter(Match.id == match_id).first()
    if match:
        match.is_visible = not match.is_visible
        db.commit()
    return RedirectResponse("/admin/matches", status_code=302)


@router.post("/matches/bulk-show-days")
async def bulk_show_days(
    request: Request,
    admin_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Set a rolling visibility window for upcoming matches.
    Matches within the next N days → visible.
    Matches beyond N days → hidden.
    Finished matches are not touched (their grace period handles visibility).
    """
    from datetime import timedelta
    form = await request.form()
    try:
        days = int(form.get("days", 3))
        now = datetime.now(timezone.utc)
        until = now + timedelta(days=days)

        shown = (
            db.query(Match)
            .filter(Match.is_finished == False, Match.kickoff_utc <= until)
            .update({"is_visible": True}, synchronize_session=False)
        )
        hidden = (
            db.query(Match)
            .filter(Match.is_finished == False, Match.kickoff_utc > until)
            .update({"is_visible": False}, synchronize_session=False)
        )
        db.commit()
        flash(request, f"Window set: {shown} match(es) visible, {hidden} hidden.", "success")
    except Exception as e:
        flash(request, f"Error: {e}", "error")
    return RedirectResponse("/admin/matches", status_code=302)


@router.post("/matches")
async def create_match(
    request: Request,
    admin_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    form = await request.form()
    try:
        match = Match(
            phase_id=int(form["phase_id"]),
            team1_code=str(form["team1_code"]).lower().strip(),
            team1_name=str(form["team1_name"]).strip(),
            team2_code=str(form["team2_code"]).lower().strip(),
            team2_name=str(form["team2_name"]).strip(),
            kickoff_utc=_parse_kickoff(str(form["kickoff_utc"])),
        )
        db.add(match)
        db.commit()
        flash(request, "Match created.", "success")
    except Exception as e:
        flash(request, f"Error: {e}", "error")
    return RedirectResponse("/admin/matches", status_code=302)


@router.get("/matches/{match_id}/edit")
async def edit_match_form(
    match_id: int,
    request: Request,
    admin_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    match = db.query(Match).options(joinedload(Match.phase)).filter(Match.id == match_id).first()
    if not match:
        return RedirectResponse("/admin/matches", status_code=302)
    phases = db.query(Phase).order_by(Phase.order_index).all()
    return templates.TemplateResponse(
        "admin/match_edit.html",
        {
            "request": request,
            "current_user": admin_user,
            "flashes": get_flashes(request),
            "match": match,
            "phases": phases,
            "to_local": _to_local,
        },
    )


@router.post("/matches/{match_id}/edit")
async def edit_match(
    match_id: int,
    request: Request,
    admin_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    match = db.query(Match).filter(Match.id == match_id).first()
    if not match:
        return RedirectResponse("/admin/matches", status_code=302)
    form = await request.form()
    try:
        match.phase_id = int(form["phase_id"])
        match.team1_code = str(form["team1_code"]).lower().strip()
        match.team1_name = str(form["team1_name"]).strip()
        match.team2_code = str(form["team2_code"]).lower().strip()
        match.team2_name = str(form["team2_name"]).strip()
        match.kickoff_utc = _parse_kickoff(str(form["kickoff_utc"]))
        db.commit()
        flash(request, "Match updated.", "success")
    except Exception as e:
        flash(request, f"Error: {e}", "error")
    return RedirectResponse("/admin/matches", status_code=302)


@router.post("/matches/{match_id}/delete")
async def delete_match(
    match_id: int,
    request: Request,
    admin_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    match = db.query(Match).filter(Match.id == match_id).first()
    if not match:
        flash(request, "Match not found.", "error")
        return RedirectResponse("/admin/matches", status_code=302)

    match_desc = f"{match.team1_name} vs {match.team2_name}"
    db.query(PredictionLog).filter(PredictionLog.match_id == match_id).delete()
    db.query(ResultLog).filter(ResultLog.match_id == match_id).delete()
    db.query(Prediction).filter(Prediction.match_id == match_id).delete()
    db.delete(match)
    db.commit()
    flash(request, f"Match '{match_desc}' deleted.", "success")
    return RedirectResponse("/admin/matches", status_code=302)


# ---------------------------------------------------------------------------
# Result entry
# ---------------------------------------------------------------------------

@router.get("/matches/{match_id}/result")
async def result_form(
    match_id: int,
    request: Request,
    admin_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    match = db.query(Match).options(joinedload(Match.phase)).filter(Match.id == match_id).first()
    if not match:
        return RedirectResponse("/admin/matches", status_code=302)
    return templates.TemplateResponse(
        "admin/result.html",
        {
            "request": request,
            "current_user": admin_user,
            "flashes": get_flashes(request),
            "match": match,
            "to_local": _to_local,
        },
    )


@router.post("/matches/{match_id}/result")
async def enter_result(
    match_id: int,
    request: Request,
    admin_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    form = await request.form()
    try:
        goals1 = int(form["goals1"])
        goals2 = int(form["goals2"])
        if not (0 <= goals1 <= 99 and 0 <= goals2 <= 99):
            raise ValueError("Goals must be between 0 and 99.")
        result_service.enter_result(db, match_id, goals1, goals2, admin_user)
        flash(request, "Result saved and points recomputed.", "success")
    except Exception as e:
        flash(request, f"Error: {e}", "error")
    return RedirectResponse("/admin/matches", status_code=302)


# ---------------------------------------------------------------------------
# Result change log
# ---------------------------------------------------------------------------

@router.get("/log")
async def result_log(
    request: Request,
    admin_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    logs = (
        db.query(ResultLog)
        .options(joinedload(ResultLog.match), joinedload(ResultLog.changed_by_user))
        .order_by(ResultLog.changed_at.desc())
        .limit(500)
        .all()
    )
    return templates.TemplateResponse(
        "admin/log.html",
        {
            "request": request,
            "current_user": admin_user,
            "flashes": get_flashes(request),
            "logs": logs,
            "to_local": _to_local,
        },
    )


# ---------------------------------------------------------------------------
# Prediction audit log (NEW)
# ---------------------------------------------------------------------------

@router.get("/prediction-log")
async def prediction_log(
    request: Request,
    admin_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
    user_id: int = None,
    match_id: int = None,
):
    query = (
        db.query(PredictionLog)
        .options(
            joinedload(PredictionLog.user),
            joinedload(PredictionLog.match).joinedload(Match.phase),
            joinedload(PredictionLog.changed_by_user),
        )
        .order_by(PredictionLog.changed_at.desc())
    )
    if user_id:
        query = query.filter(PredictionLog.user_id == user_id)
    if match_id:
        query = query.filter(PredictionLog.match_id == match_id)

    logs = query.limit(1000).all()
    users = db.query(User).order_by(User.username).all()
    matches = db.query(Match).options(joinedload(Match.phase)).order_by(Match.kickoff_utc).all()

    return templates.TemplateResponse(
        "admin/prediction_log.html",
        {
            "request": request,
            "current_user": admin_user,
            "flashes": get_flashes(request),
            "logs": logs,
            "users": users,
            "matches": matches,
            "filter_user_id": user_id,
            "filter_match_id": match_id,
            "to_local": _to_local,
        },
    )


# ---------------------------------------------------------------------------
# League management
# ---------------------------------------------------------------------------

@router.get("/leagues")
async def leagues_list(
    request: Request,
    admin_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    leagues = db.query(League).order_by(League.name).all()
    all_users = db.query(User).order_by(User.username).all()
    member_map: dict[int, list] = {}
    for league in leagues:
        member_ids = [
            ul.user_id
            for ul in db.query(UserLeague).filter(UserLeague.league_id == league.id).all()
        ]
        member_map[league.id] = db.query(User).filter(User.id.in_(member_ids)).order_by(User.username).all()
    return templates.TemplateResponse(
        "admin/leagues.html",
        {
            "request": request,
            "current_user": admin_user,
            "flashes": get_flashes(request),
            "leagues": leagues,
            "all_users": all_users,
            "member_map": member_map,
        },
    )


@router.post("/leagues")
async def create_league(
    request: Request,
    admin_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    form = await request.form()
    name = str(form.get("name", "")).strip()
    if not name:
        flash(request, "League name is required.", "error")
        return RedirectResponse("/admin/leagues", status_code=302)
    if db.query(League).filter(League.name == name).first():
        flash(request, f"League '{name}' already exists.", "error")
        return RedirectResponse("/admin/leagues", status_code=302)
    db.add(League(name=name))
    db.commit()
    flash(request, f"League '{name}' created.", "success")
    return RedirectResponse("/admin/leagues", status_code=302)


@router.post("/leagues/{league_id}/add-user")
async def league_add_user(
    league_id: int,
    request: Request,
    admin_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    form = await request.form()
    user_id = int(form.get("user_id", 0))
    if not db.query(UserLeague).filter(
        UserLeague.league_id == league_id, UserLeague.user_id == user_id
    ).first():
        db.add(UserLeague(user_id=user_id, league_id=league_id))
        db.commit()
        flash(request, "User added to league.", "success")
    else:
        flash(request, "User is already in this league.", "warning")
    return RedirectResponse("/admin/leagues", status_code=302)


@router.post("/leagues/{league_id}/remove-user/{user_id}")
async def league_remove_user(
    league_id: int,
    user_id: int,
    request: Request,
    admin_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    db.query(UserLeague).filter(
        UserLeague.league_id == league_id, UserLeague.user_id == user_id
    ).delete()
    db.commit()
    flash(request, "User removed from league.", "success")
    return RedirectResponse("/admin/leagues", status_code=302)


@router.get("/leagues/{league_id}/edit")
async def league_edit_form(
    league_id: int,
    request: Request,
    admin_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    league = db.query(League).filter(League.id == league_id).first()
    if not league:
        return RedirectResponse("/admin/leagues", status_code=302)
    return templates.TemplateResponse(
        "admin/league_edit.html",
        {
            "request": request,
            "current_user": admin_user,
            "flashes": get_flashes(request),
            "league": league,
        },
    )


@router.post("/leagues/{league_id}/edit")
async def edit_league(
    league_id: int,
    request: Request,
    admin_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    league = db.query(League).filter(League.id == league_id).first()
    if not league:
        flash(request, "League not found.", "error")
        return RedirectResponse("/admin/leagues", status_code=302)

    form = await request.form()
    new_name = str(form.get("name", "")).strip()
    if not new_name:
        flash(request, "League name is required.", "error")
        return RedirectResponse("/admin/leagues", status_code=302)

    if new_name != league.name and db.query(League).filter(League.name == new_name).first():
        flash(request, f"League '{new_name}' already exists.", "error")
        return RedirectResponse("/admin/leagues", status_code=302)

    league.name = new_name
    db.commit()
    flash(request, f"League renamed to '{new_name}'.", "success")
    return RedirectResponse("/admin/leagues", status_code=302)


@router.post("/leagues/{league_id}/delete")
async def delete_league(
    league_id: int,
    request: Request,
    admin_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    league = db.query(League).filter(League.id == league_id).first()
    if not league:
        flash(request, "League not found.", "error")
        return RedirectResponse("/admin/leagues", status_code=302)

    league_name = league.name
    from app.models.models import UserBadge
    db.query(UserBadge).filter(UserBadge.league_id == league_id).delete()
    db.query(UserLeague).filter(UserLeague.league_id == league_id).delete()
    db.delete(league)
    db.commit()
    flash(request, f"League '{league_name}' deleted. Users remain registered.", "success")
    return RedirectResponse("/admin/leagues", status_code=302)
