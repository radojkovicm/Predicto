from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.models import Match, Prediction, User
from app.services import lock_service
from config.config import settings

router = APIRouter()
_bearer = HTTPBearer(auto_error=False)


def _verify_token(credentials: HTTPAuthorizationCredentials = Depends(_bearer)):
    if not credentials or credentials.credentials != settings.REMINDER_API_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid or missing token.")
    return credentials.credentials


@router.get("/reminder-data")
async def reminder_data(
    request: Request,
    _: str = Depends(_verify_token),
    db: Session = Depends(get_db),
):
    """Returns users who haven't predicted today's upcoming (unlocked) matches.
    Consumed by n8n for sending reminders — the app just provides the data.
    """
    now = datetime.now(timezone.utc)
    today_end = now.replace(hour=23, minute=59, second=59, microsecond=999999)

    upcoming = (
        db.query(Match)
        .filter(
            Match.kickoff_utc >= now,
            Match.kickoff_utc <= today_end,
            Match.is_finished == False,
        )
        .all()
    )

    unlocked = [m for m in upcoming if not lock_service.is_locked(m)]
    if not unlocked:
        return {"users": []}

    unlocked_ids = {m.id for m in unlocked}
    all_users = db.query(User).all()

    result = []
    for user in all_users:
        predicted_ids = {
            p.match_id
            for p in db.query(Prediction.match_id)
            .filter(Prediction.user_id == user.id, Prediction.match_id.in_(unlocked_ids))
            .all()
        }
        missing = list(unlocked_ids - predicted_ids)
        if missing:
            result.append(
                {
                    "user_id": user.id,
                    "username": user.username,
                    "missing_match_ids": sorted(missing),
                }
            )

    return {"users": result}
