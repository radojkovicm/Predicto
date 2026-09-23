from datetime import datetime, timezone
from sqlalchemy.orm import Session

from app.models.models import Match, Prediction, PredictionLog
from app.models.models import User
from app.services import lock_service


def save_prediction(
    db: Session,
    user: User,
    match: Match,
    pred_goals1: int,
    pred_goals2: int,
    is_joker: bool,
) -> Prediction:
    """Create or update a prediction. Enforces lock and joker-per-phase rules.

    Also writes a PredictionLog entry for every change (audit trail).
    """
    if not match.is_visible:
        raise ValueError("This match is not open for predictions yet.")

    if lock_service.is_locked(match):
        raise ValueError("This match is locked — predictions are closed.")

    if match.competition.status != "active":
        raise ValueError("This competition isn't open for predictions right now.")

    existing = db.query(Prediction).filter(
        Prediction.user_id == user.id,
        Prediction.match_id == match.id,
    ).first()

    if is_joker:
        # Count jokers already used by this user in this phase (excluding this prediction)
        jokers_in_phase_query = (
            db.query(Prediction)
            .join(Match, Prediction.match_id == Match.id)
            .filter(
                Prediction.user_id == user.id,
                Match.phase_id == match.phase_id,
                Prediction.is_joker == True,
            )
        )
        if existing is not None:
            jokers_in_phase_query = jokers_in_phase_query.filter(Prediction.id != existing.id)
        jokers_in_phase = jokers_in_phase_query.count()

        jokers_per_phase = match.competition.jokers_per_phase
        if jokers_in_phase >= jokers_per_phase:
            raise ValueError("You already used your joker for this phase.")

    now = datetime.now(timezone.utc)

    if existing:
        log = PredictionLog(
            prediction_id=existing.id,
            user_id=user.id,
            match_id=match.id,
            old_goals1=existing.pred_goals1,
            old_goals2=existing.pred_goals2,
            new_goals1=pred_goals1,
            new_goals2=pred_goals2,
            changed_by=user.id,
        )
        db.add(log)
        existing.pred_goals1 = pred_goals1
        existing.pred_goals2 = pred_goals2
        existing.is_joker = is_joker
        existing.updated_at = now
        db.commit()
        db.refresh(existing)
        return existing

    pred = Prediction(
        user_id=user.id,
        match_id=match.id,
        pred_goals1=pred_goals1,
        pred_goals2=pred_goals2,
        is_joker=is_joker,
        created_at=now,
        updated_at=now,
    )
    db.add(pred)
    db.flush()  # get pred.id before log

    log = PredictionLog(
        prediction_id=pred.id,
        user_id=user.id,
        match_id=match.id,
        old_goals1=None,
        old_goals2=None,
        new_goals1=pred_goals1,
        new_goals2=pred_goals2,
        changed_by=user.id,
    )
    db.add(log)
    db.commit()
    db.refresh(pred)
    return pred
