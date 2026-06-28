from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.auth.deps import require_login
from app.auth.flash import flash
from app.db import get_db
from app.models.models import Match, User
from app.services import prediction_service

router = APIRouter()


@router.post("/predictions")
async def save_prediction(
    request: Request,
    current_user: User = Depends(require_login),
    db: Session = Depends(get_db),
):
    form = await request.form()

    try:
        match_id = int(form["match_id"])
        pred_goals1 = int(form["pred_goals1"])
        pred_goals2 = int(form["pred_goals2"])
        is_joker = form.get("is_joker") == "1"
    except (KeyError, ValueError):
        flash(request, "Invalid prediction data.", "error")
        return RedirectResponse("/matches", status_code=302)

    if not (0 <= pred_goals1 <= 99 and 0 <= pred_goals2 <= 99):
        flash(request, "Goals must be between 0 and 99.", "error")
        return RedirectResponse(f"/matches/{match_id}", status_code=302)

    match = db.query(Match).filter(Match.id == match_id).first()
    if not match:
        flash(request, "Match not found.", "error")
        return RedirectResponse("/matches", status_code=302)

    try:
        prediction_service.save_prediction(
            db, current_user, match, pred_goals1, pred_goals2, is_joker
        )
        flash(request, "✅ Prediction saved!", "success")
    except ValueError as e:
        flash(request, str(e), "error")
        return RedirectResponse(f"/matches/{match_id}", status_code=302)

    return RedirectResponse("/matches", status_code=302)
