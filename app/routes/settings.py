from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.auth.deps import require_login
from app.auth.flash import flash, get_flashes
from app.auth.password import hash_password, verify_password
from app.db import get_db
from app.models.models import User

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/settings")
async def settings_page(
    request: Request,
    current_user: User = Depends(require_login),
):
    return templates.TemplateResponse(
        "settings.html",
        {
            "request": request,
            "current_user": current_user,
            "flashes": get_flashes(request),
        },
    )


@router.post("/settings/name")
async def update_name(
    request: Request,
    current_user: User = Depends(require_login),
    db: Session = Depends(get_db),
):
    form = await request.form()
    first_name = str(form.get("first_name", "")).strip()
    last_name = str(form.get("last_name", "")).strip()

    current_user.first_name = first_name or None
    current_user.last_name = last_name or None
    db.commit()
    flash(request, "Name updated successfully.", "success")
    return RedirectResponse("/settings", status_code=302)


@router.post("/settings/password")
async def change_password(
    request: Request,
    current_user: User = Depends(require_login),
    db: Session = Depends(get_db),
):
    form = await request.form()
    current_pw = str(form.get("current_password", ""))
    new_pw = str(form.get("new_password", ""))
    confirm_pw = str(form.get("confirm_password", ""))

    if not verify_password(current_pw, current_user.password_hash):
        flash(request, "Current password is incorrect.", "error")
        return RedirectResponse("/settings", status_code=302)

    if len(new_pw) < 6:
        flash(request, "New password must be at least 6 characters.", "error")
        return RedirectResponse("/settings", status_code=302)

    if new_pw != confirm_pw:
        flash(request, "New passwords do not match.", "error")
        return RedirectResponse("/settings", status_code=302)

    current_user.password_hash = hash_password(new_pw)
    db.commit()
    flash(request, "Password changed successfully.", "success")
    return RedirectResponse("/settings", status_code=302)
