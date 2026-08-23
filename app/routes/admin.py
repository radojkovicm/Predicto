import pytz
from datetime import datetime, timezone
from io import BytesIO
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from app.auth.csrf import csrf_token
from app.auth.deps import require_admin
from app.auth.flash import flash, get_flashes
from app.auth.password import hash_password
from app.db import get_db
from app.models.models import (
    Competition, League, Match, Phase, Prediction, PredictionLog, ResultLog, User, UserBadge, UserLeague
)
from app.services import badge_service, match_import_service, ranking_service, result_service

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")
templates.env.globals["csrf_token"] = csrf_token
TZ_DISPLAY = pytz.timezone("Europe/Ljubljana")
LEAGUE_ARCHIVE_SUFFIX = " (archived)"


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


def _resolve_competition(
    db: Session,
    requested_id: Optional[int],
    include_finished: bool = True,
) -> tuple[Optional[Competition], list[Competition]]:
    """Returns (selected_competition, all_competitions).
    Priority for the default: prefer active, else most recent finished, else most recent by id.
    Mirrors league_service.resolve_league's "pick from query param, else sensible default" pattern.

    include_finished=False drops finished competitions entirely — for the day-to-day
    working views (matches, results, prediction log) where a finished competition has
    nothing left to do; it stays fully visible in /admin/archive regardless.
    """
    competitions = db.query(Competition).order_by(Competition.id.desc()).all()
    if not include_finished:
        competitions = [c for c in competitions if c.status != "finished"]
    if not competitions:
        return None, []
    if requested_id:
        requested = next((c for c in competitions if c.id == requested_id), None)
        if requested:
            return requested, competitions
    default = (
        next((c for c in competitions if c.status == "active"), None)
        or next((c for c in competitions if c.status == "finished"), None)
        or competitions[0]
    )
    return default, competitions


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


@router.post("/users/{user_id}/approve")
async def approve_user(
    user_id: int,
    request: Request,
    admin_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        flash(request, "User not found.", "error")
    else:
        user.is_approved = True
        db.commit()
        flash(request, f"'{user.username}' approved — they can now log in.", "success")
    return RedirectResponse("/admin/users", status_code=302)


@router.post("/users/{user_id}/delete")
async def delete_user(
    user_id: int,
    request: Request,
    admin_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Soft delete — the account can no longer log in, but its predictions,
    badges and log entries stay intact so leaderboards and audit trails don't
    develop holes. See [[security-todos]] in project memory for why.
    """
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        flash(request, "User not found.", "error")
        return RedirectResponse("/admin/users", status_code=302)
    if user_id == admin_user.id:
        flash(request, "You cannot delete your own account.", "error")
        return RedirectResponse("/admin/users", status_code=302)

    user.deleted_at = datetime.now(timezone.utc)
    db.commit()
    flash(request, f"User '{user.username}' deleted (predictions and history are kept).", "success")
    return RedirectResponse("/admin/users", status_code=302)


# ---------------------------------------------------------------------------
# Matches
# ---------------------------------------------------------------------------

@router.get("/matches")
async def matches_list(
    request: Request,
    admin_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
    competition_id: Optional[int] = None,
):
    selected_competition, competitions = _resolve_competition(db, competition_id, include_finished=False)
    matches = (
        db.query(Match)
        .options(joinedload(Match.phase))
        .filter(Match.competition_id == selected_competition.id)
        .order_by(Match.kickoff_utc)
        .all()
        if selected_competition else []
    )
    phases = (
        db.query(Phase)
        .filter(Phase.competition_id == selected_competition.id)
        .order_by(Phase.order_index)
        .all()
        if selected_competition else []
    )
    visible_count = sum(1 for m in matches if m.is_visible)
    return templates.TemplateResponse(
        "admin/matches.html",
        {
            "request": request,
            "current_user": admin_user,
            "flashes": get_flashes(request),
            "matches": matches,
            "phases": phases,
            "competitions": competitions,
            "selected_competition": selected_competition,
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
        phase = db.query(Phase).filter(Phase.id == int(form["phase_id"])).first()
        if not phase:
            raise ValueError("Phase not found.")
        match = Match(
            phase_id=phase.id,
            competition_id=phase.competition_id,
            team1_code=str(form["team1_code"]).lower().strip(),
            team1_name=str(form["team1_name"]).strip(),
            team2_code=str(form["team2_code"]).lower().strip(),
            team2_name=str(form["team2_name"]).strip(),
            kickoff_utc=_parse_kickoff(str(form["kickoff_utc"])),
        )
        db.add(match)
        db.commit()
        flash(request, "Match created.", "success")
        return RedirectResponse(f"/admin/matches?competition_id={phase.competition_id}", status_code=302)
    except Exception as e:
        flash(request, f"Error: {e}", "error")
    return RedirectResponse("/admin/matches", status_code=302)


@router.get("/matches/upload-template")
async def matches_upload_template(
    competition_id: int,
    admin_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    competition = db.query(Competition).filter(Competition.id == competition_id).first()
    if not competition:
        return RedirectResponse("/admin/matches", status_code=302)

    phases = (
        db.query(Phase)
        .filter(Phase.competition_id == competition_id)
        .order_by(Phase.order_index)
        .all()
    )
    wb = match_import_service.build_template_workbook(phases)
    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)

    filename = f"{competition.name.replace(' ', '_')}_matches_template.xlsx"
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/matches/upload")
async def matches_upload(
    request: Request,
    competition_id: int = Form(...),
    file: UploadFile = File(...),
    admin_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    competition = db.query(Competition).filter(Competition.id == competition_id).first()
    if not competition:
        flash(request, "Competition not found.", "error")
        return RedirectResponse("/admin/matches", status_code=302)
    if competition.status == "finished":
        flash(request, "This competition is finished — see it in the archive instead.", "error")
        return RedirectResponse("/admin/matches", status_code=302)

    try:
        file_bytes = await file.read()
        added, messages = match_import_service.parse_upload(db, file_bytes, competition_id)
    except Exception as e:
        flash(request, f"Couldn't read that file: {e}", "error")
        return RedirectResponse(f"/admin/matches?competition_id={competition_id}", status_code=302)

    if added:
        flash(request, f"Added {added} match(es) to '{competition.name}'.", "success")
    if messages:
        flash(request, f"{len(messages)} row(s) skipped: " + " | ".join(messages), "warning")
    if not added and not messages:
        flash(request, "No rows found in that file.", "warning")
    return RedirectResponse(f"/admin/matches?competition_id={competition_id}", status_code=302)


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
    phases = (
        db.query(Phase)
        .filter(Phase.competition_id == match.competition_id)
        .order_by(Phase.order_index)
        .all()
    )
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
        phase = db.query(Phase).filter(Phase.id == int(form["phase_id"])).first()
        if not phase:
            raise ValueError("Phase not found.")
        match.phase_id = phase.id
        match.competition_id = phase.competition_id
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
    if not match or match.competition.status == "finished":
        flash(request, "This competition is finished — see it in the archive instead.", "error")
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
    # Same reasoning as /prediction-log: a finished competition has nothing
    # left to audit day-to-day; its logs stay intact, just hidden from here.
    not_finished_match_ids = (
        db.query(Match.id)
        .join(Competition, Match.competition_id == Competition.id)
        .filter(Competition.status != "finished")
    )
    logs = (
        db.query(ResultLog)
        .options(joinedload(ResultLog.match), joinedload(ResultLog.changed_by_user))
        .filter(ResultLog.match_id.in_(not_finished_match_ids))
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
    # Finished competitions have nothing left to audit here day-to-day —
    # their logs stay fully intact in the DB, just not shown in this working view.
    not_finished_match_ids = (
        db.query(Match.id)
        .join(Competition, Match.competition_id == Competition.id)
        .filter(Competition.status != "finished")
    )

    query = (
        db.query(PredictionLog)
        .options(
            joinedload(PredictionLog.user),
            joinedload(PredictionLog.match).joinedload(Match.phase),
            joinedload(PredictionLog.changed_by_user),
        )
        .filter(PredictionLog.match_id.in_(not_finished_match_ids))
        .order_by(PredictionLog.changed_at.desc())
    )
    if user_id:
        query = query.filter(PredictionLog.user_id == user_id)
    if match_id:
        query = query.filter(PredictionLog.match_id == match_id)

    logs = query.limit(1000).all()
    users = db.query(User).order_by(User.username).all()
    matches = (
        db.query(Match)
        .options(joinedload(Match.phase))
        .join(Competition, Match.competition_id == Competition.id)
        .filter(Competition.status != "finished")
        .order_by(Match.kickoff_utc)
        .all()
    )

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
    competition_id: Optional[int] = None,
):
    leagues = db.query(League).order_by(League.name).all()
    all_users = db.query(User).order_by(User.username).all()
    selected_competition, competitions = _resolve_competition(db, competition_id)
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
            "competitions": competitions,
            "selected_competition": selected_competition,
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
    competition = None
    raw_competition_id = form.get("competition_id")
    if raw_competition_id:
        competition = db.query(Competition).filter(Competition.id == int(raw_competition_id)).first()
    if not competition:
        competition, _ = _resolve_competition(db, None)
    if not competition:
        flash(request, "No competition exists yet — create one first.", "error")
        return RedirectResponse("/admin/leagues", status_code=302)

    if db.query(League).filter(League.name == name, League.competition_id == competition.id).first():
        flash(request, f"League '{name}' already exists.", "error")
        return RedirectResponse("/admin/leagues", status_code=302)

    db.add(League(name=name, competition_id=competition.id))
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


@router.post("/leagues/{league_id}/generate-invite")
async def league_generate_invite(
    league_id: int,
    request: Request,
    admin_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    import secrets

    league = db.query(League).filter(League.id == league_id).first()
    if not league:
        flash(request, "League not found.", "error")
        return RedirectResponse("/admin/leagues", status_code=302)

    for _ in range(10):
        code = secrets.token_urlsafe(6)
        if not db.query(League).filter(League.join_code == code).first():
            league.join_code = code
            db.commit()
            flash(request, f"Invite link generated for '{league.name}'.", "success")
            break
    else:
        flash(request, "Could not generate a unique invite code — try again.", "error")
    return RedirectResponse("/admin/leagues", status_code=302)


@router.post("/leagues/{league_id}/revoke-invite")
async def league_revoke_invite(
    league_id: int,
    request: Request,
    admin_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    league = db.query(League).filter(League.id == league_id).first()
    if league:
        league.join_code = None
        db.commit()
        flash(request, f"Invite link revoked for '{league.name}'.", "success")
    return RedirectResponse("/admin/leagues", status_code=302)


@router.post("/leagues/{league_id}/archive")
async def league_archive(
    league_id: int,
    request: Request,
    admin_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Retire one league early — its members stop seeing it in ranking/profile
    even though its competition (and any other leagues in it) stay active.
    The name gets an " (archived)" suffix so it can't be confused with a live
    league later, and so the original name is free if reused for a new season.
    """
    league = db.query(League).filter(League.id == league_id).first()
    if league:
        league.archived_at = datetime.now(timezone.utc)
        if not league.name.endswith(LEAGUE_ARCHIVE_SUFFIX):
            league.name = f"{league.name}{LEAGUE_ARCHIVE_SUFFIX}"
        db.commit()
        flash(request, f"'{league.name}' archived — hidden from members, still readable here.", "success")
    return RedirectResponse("/admin/leagues", status_code=302)


@router.post("/leagues/{league_id}/unarchive")
async def league_unarchive(
    league_id: int,
    request: Request,
    admin_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    league = db.query(League).filter(League.id == league_id).first()
    if league:
        league.archived_at = None
        if league.name.endswith(LEAGUE_ARCHIVE_SUFFIX):
            league.name = league.name[: -len(LEAGUE_ARCHIVE_SUFFIX)]
        db.commit()
        flash(request, f"'{league.name}' unarchived — visible to members again.", "success")
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

    if new_name != league.name and db.query(League).filter(
        League.name == new_name, League.competition_id == league.competition_id
    ).first():
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


# ---------------------------------------------------------------------------
# Competition management
# ---------------------------------------------------------------------------

@router.get("/competitions")
async def competitions_list(
    request: Request,
    admin_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    competitions = db.query(Competition).order_by(Competition.id.desc()).all()
    return templates.TemplateResponse(
        "admin/competitions.html",
        {
            "request": request,
            "current_user": admin_user,
            "flashes": get_flashes(request),
            "competitions": competitions,
            "to_local": _to_local,
        },
    )


@router.get("/competitions/new")
async def new_competition_form(
    request: Request,
    admin_user: User = Depends(require_admin),
):
    return templates.TemplateResponse(
        "admin/competition_edit.html",
        {
            "request": request,
            "current_user": admin_user,
            "flashes": get_flashes(request),
            "competition": None,
            "phases": [],
        },
    )


@router.post("/competitions/new")
async def create_competition(
    request: Request,
    admin_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    form = await request.form()
    name = str(form.get("name", "")).strip()
    if not name:
        flash(request, "Competition name is required.", "error")
        return RedirectResponse("/admin/competitions/new", status_code=302)
    if db.query(Competition).filter(Competition.name == name).first():
        flash(request, f"Competition '{name}' already exists.", "error")
        return RedirectResponse("/admin/competitions/new", status_code=302)

    try:
        competition = Competition(
            name=name,
            status="draft",
            points_outcome=int(form.get("points_outcome", 10)),
            points_goal_diff=int(form.get("points_goal_diff", 7)),
            points_goal_home=int(form.get("points_goal_home", 4)),
            points_goal_away=int(form.get("points_goal_away", 4)),
            joker_bonus=int(form.get("joker_bonus", 8)),
            joker_penalty=int(form.get("joker_penalty", -5)),
            jokers_per_phase=int(form.get("jokers_per_phase", 1)),
            notes=str(form.get("notes", "")).strip() or None,
        )
        db.add(competition)
        db.commit()
        flash(request, f"Competition '{name}' created as draft.", "success")
        return RedirectResponse(f"/admin/competitions/{competition.id}/edit", status_code=302)
    except Exception as e:
        flash(request, f"Error: {e}", "error")
        return RedirectResponse("/admin/competitions/new", status_code=302)


@router.get("/competitions/{competition_id}/edit")
async def edit_competition_form(
    competition_id: int,
    request: Request,
    admin_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    competition = db.query(Competition).filter(Competition.id == competition_id).first()
    if not competition:
        flash(request, "Competition not found.", "error")
        return RedirectResponse("/admin/competitions", status_code=302)
    phases = (
        db.query(Phase)
        .filter(Phase.competition_id == competition_id)
        .order_by(Phase.order_index)
        .all()
    )
    return templates.TemplateResponse(
        "admin/competition_edit.html",
        {
            "request": request,
            "current_user": admin_user,
            "flashes": get_flashes(request),
            "competition": competition,
            "phases": phases,
        },
    )


@router.post("/competitions/{competition_id}/edit")
async def edit_competition(
    competition_id: int,
    request: Request,
    admin_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    competition = db.query(Competition).filter(Competition.id == competition_id).first()
    if not competition:
        flash(request, "Competition not found.", "error")
        return RedirectResponse("/admin/competitions", status_code=302)
    if competition.status == "finished":
        flash(request, "Finished competitions are immutable history and cannot be edited.", "error")
        return RedirectResponse(f"/admin/competitions/{competition_id}/edit", status_code=302)

    form = await request.form()
    new_name = str(form.get("name", "")).strip()
    if not new_name:
        flash(request, "Competition name is required.", "error")
        return RedirectResponse(f"/admin/competitions/{competition_id}/edit", status_code=302)
    if new_name != competition.name and db.query(Competition).filter(Competition.name == new_name).first():
        flash(request, f"Competition '{new_name}' already exists.", "error")
        return RedirectResponse(f"/admin/competitions/{competition_id}/edit", status_code=302)

    try:
        competition.name = new_name
        competition.points_outcome = int(form.get("points_outcome", competition.points_outcome))
        competition.points_goal_diff = int(form.get("points_goal_diff", competition.points_goal_diff))
        competition.points_goal_home = int(form.get("points_goal_home", competition.points_goal_home))
        competition.points_goal_away = int(form.get("points_goal_away", competition.points_goal_away))
        competition.joker_bonus = int(form.get("joker_bonus", competition.joker_bonus))
        competition.joker_penalty = int(form.get("joker_penalty", competition.joker_penalty))
        competition.jokers_per_phase = int(form.get("jokers_per_phase", competition.jokers_per_phase))
        competition.notes = str(form.get("notes", "")).strip() or None
        db.commit()
        flash(request, f"Competition '{new_name}' updated.", "success")
    except Exception as e:
        flash(request, f"Error: {e}", "error")
    return RedirectResponse(f"/admin/competitions/{competition_id}/edit", status_code=302)


@router.post("/competitions/{competition_id}/activate")
async def activate_competition(
    competition_id: int,
    request: Request,
    admin_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    competition = db.query(Competition).filter(Competition.id == competition_id).first()
    if not competition:
        flash(request, "Competition not found.", "error")
        return RedirectResponse("/admin/competitions", status_code=302)
    if competition.status == "finished":
        flash(request, "Finished competitions cannot be reactivated.", "error")
        return RedirectResponse("/admin/competitions", status_code=302)

    other_active = (
        db.query(Competition)
        .filter(Competition.status == "active", Competition.id != competition_id)
        .first()
    )
    if other_active:
        flash(
            request,
            f"'{other_active.name}' is already active. Finish it before activating another competition.",
            "error",
        )
        return RedirectResponse("/admin/competitions", status_code=302)

    competition.status = "active"
    db.commit()
    flash(request, f"Competition '{competition.name}' activated.", "success")
    return RedirectResponse("/admin/competitions", status_code=302)


@router.post("/competitions/{competition_id}/finish")
async def finish_competition(
    competition_id: int,
    request: Request,
    admin_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    competition = db.query(Competition).filter(Competition.id == competition_id).first()
    if not competition:
        flash(request, "Competition not found.", "error")
        return RedirectResponse("/admin/competitions", status_code=302)
    if competition.status == "finished":
        flash(request, "Competition is already finished.", "warning")
        return RedirectResponse("/admin/competitions", status_code=302)

    competition.status = "finished"
    competition.finished_at = datetime.now(timezone.utc)
    db.commit()
    flash(request, f"Competition '{competition.name}' finished. It is now read-only history.", "success")
    return RedirectResponse("/admin/competitions", status_code=302)


@router.post("/competitions/{competition_id}/reopen")
async def reopen_competition(
    competition_id: int,
    request: Request,
    admin_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    competition = db.query(Competition).filter(Competition.id == competition_id).first()
    if not competition:
        flash(request, "Competition not found.", "error")
        return RedirectResponse("/admin/competitions", status_code=302)
    if competition.status != "finished":
        flash(request, "Only finished competitions can be reopened.", "error")
        return RedirectResponse("/admin/competitions", status_code=302)

    other_active = (
        db.query(Competition)
        .filter(Competition.status == "active", Competition.id != competition_id)
        .first()
    )
    if other_active:
        flash(
            request,
            f"'{other_active.name}' is already active. Finish it before reopening another competition.",
            "error",
        )
        return RedirectResponse("/admin/competitions", status_code=302)

    competition.status = "active"
    competition.finished_at = None
    db.commit()
    flash(request, f"Competition '{competition.name}' reopened — it is live again for all users.", "success")
    return RedirectResponse("/admin/competitions", status_code=302)


# ---------------------------------------------------------------------------
# Phase management (nested under a competition)
# ---------------------------------------------------------------------------

@router.post("/competitions/{competition_id}/phases")
async def create_phase(
    competition_id: int,
    request: Request,
    admin_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    competition = db.query(Competition).filter(Competition.id == competition_id).first()
    if not competition:
        flash(request, "Competition not found.", "error")
        return RedirectResponse("/admin/competitions", status_code=302)
    if competition.status == "finished":
        flash(request, "Finished competitions are immutable history — cannot add phases.", "error")
        return RedirectResponse(f"/admin/competitions/{competition_id}/edit", status_code=302)

    form = await request.form()
    try:
        phase = Phase(
            competition_id=competition_id,
            name=str(form["name"]).strip(),
            order_index=int(form["order_index"]),
            joker_allowed=form.get("joker_allowed") == "1",
            is_group_stage=form.get("is_group_stage") == "1",
            point_multiplier=float(form.get("point_multiplier", 1.00)),
        )
        db.add(phase)
        db.commit()
        flash(request, f"Phase '{phase.name}' created.", "success")
    except Exception as e:
        flash(request, f"Error: {e}", "error")
    return RedirectResponse(f"/admin/competitions/{competition_id}/edit", status_code=302)


@router.get("/competitions/{competition_id}/phases/{phase_id}/edit")
async def edit_phase_form(
    competition_id: int,
    phase_id: int,
    request: Request,
    admin_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    phase = db.query(Phase).filter(Phase.id == phase_id, Phase.competition_id == competition_id).first()
    if not phase:
        flash(request, "Phase not found.", "error")
        return RedirectResponse(f"/admin/competitions/{competition_id}/edit", status_code=302)
    return templates.TemplateResponse(
        "admin/phase_edit.html",
        {
            "request": request,
            "current_user": admin_user,
            "flashes": get_flashes(request),
            "phase": phase,
        },
    )


@router.post("/competitions/{competition_id}/phases/{phase_id}/edit")
async def edit_phase(
    competition_id: int,
    phase_id: int,
    request: Request,
    admin_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    phase = db.query(Phase).filter(Phase.id == phase_id, Phase.competition_id == competition_id).first()
    if not phase:
        flash(request, "Phase not found.", "error")
        return RedirectResponse(f"/admin/competitions/{competition_id}/edit", status_code=302)
    if phase.competition.status == "finished":
        flash(request, "Finished competitions are immutable history — cannot edit phases.", "error")
        return RedirectResponse(f"/admin/competitions/{competition_id}/edit", status_code=302)

    form = await request.form()
    try:
        phase.name = str(form["name"]).strip()
        phase.order_index = int(form["order_index"])
        phase.joker_allowed = form.get("joker_allowed") == "1"
        phase.is_group_stage = form.get("is_group_stage") == "1"
        phase.point_multiplier = float(form.get("point_multiplier", phase.point_multiplier))
        db.commit()
        flash(request, f"Phase '{phase.name}' updated.", "success")
    except Exception as e:
        flash(request, f"Error: {e}", "error")
    return RedirectResponse(f"/admin/competitions/{competition_id}/edit", status_code=302)


# ---------------------------------------------------------------------------
# Archive (read-only view of finished competitions)
# ---------------------------------------------------------------------------

@router.get("/archive")
async def archive_list(
    request: Request,
    admin_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    competitions = (
        db.query(Competition)
        .filter(Competition.status == "finished")
        .order_by(Competition.finished_at.desc())
        .all()
    )
    return templates.TemplateResponse(
        "admin/archive.html",
        {
            "request": request,
            "current_user": admin_user,
            "flashes": get_flashes(request),
            "competitions": competitions,
            "to_local": _to_local,
        },
    )


@router.get("/archive/{competition_id}")
async def archive_competition(
    competition_id: int,
    request: Request,
    admin_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    competition = (
        db.query(Competition)
        .filter(Competition.id == competition_id, Competition.status == "finished")
        .first()
    )
    if not competition:
        flash(request, "Archived competition not found.", "error")
        return RedirectResponse("/admin/archive", status_code=302)
    leagues = db.query(League).filter(League.competition_id == competition_id).order_by(League.name).all()
    return templates.TemplateResponse(
        "admin/archive_competition.html",
        {
            "request": request,
            "current_user": admin_user,
            "flashes": get_flashes(request),
            "competition": competition,
            "leagues": leagues,
            "to_local": _to_local,
        },
    )


@router.get("/archive/{competition_id}/leagues/{league_id}")
async def archive_league_leaderboard(
    competition_id: int,
    league_id: int,
    request: Request,
    admin_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    competition = (
        db.query(Competition)
        .filter(Competition.id == competition_id, Competition.status == "finished")
        .first()
    )
    if not competition:
        flash(request, "Archived competition not found.", "error")
        return RedirectResponse("/admin/archive", status_code=302)
    league = db.query(League).filter(League.id == league_id, League.competition_id == competition_id).first()
    if not league:
        flash(request, "League not found in this competition.", "error")
        return RedirectResponse(f"/admin/archive/{competition_id}", status_code=302)

    leaderboard = ranking_service.get_leaderboard(db, league_id)
    member_ids = [entry["user_id"] for entry in leaderboard]

    # Competition-scoped badges (personal + this league's), regardless of active/expired lifecycle —
    # this is a final historical record, not a live "currently showing" view.
    badges = (
        db.query(UserBadge)
        .filter(
            UserBadge.competition_id == competition_id,
            UserBadge.user_id.in_(member_ids),
            or_(UserBadge.league_id == league_id, UserBadge.league_id == None),
        )
        .order_by(UserBadge.awarded_at.desc())
        .all()
    )
    badges_by_user: dict[int, list] = {}
    for b in badges:
        badges_by_user.setdefault(b.user_id, []).append(b)

    joker_stats: dict[int, dict[str, int]] = {}
    for uid in member_ids:
        user_badges = badges_by_user.get(uid, [])
        joker_stats[uid] = {
            "joker_master": sum(1 for b in user_badges if b.badge_code == "joker_master"),
            "joker_victim": sum(1 for b in user_badges if b.badge_code == "joker_victim"),
        }

    return templates.TemplateResponse(
        "admin/archive_league.html",
        {
            "request": request,
            "current_user": admin_user,
            "flashes": get_flashes(request),
            "competition": competition,
            "league": league,
            "leaderboard": leaderboard,
            "badges_by_user": badges_by_user,
            "joker_stats": joker_stats,
            "badge_display": badge_service.badge_display,
            "to_local": _to_local,
        },
    )
