from sqlalchemy.orm import Session

from datetime import datetime, timezone
from app.models.models import League, Match, Prediction, ResultLog, User
from app.services.scoring_service import compute_points
from app.services.ranking_service import get_user_positions
from app.services import badge_service


def enter_result(
    db: Session,
    match_id: int,
    goals1: int,
    goals2: int,
    admin_user: User,
) -> Match:
    match = db.query(Match).filter(Match.id == match_id).first()
    if not match:
        raise ValueError(f"Match {match_id} not found.")

    # Snapshot positions per league BEFORE points change (comeback_king badge)
    leagues = db.query(League).all()
    old_positions_by_league = {
        league.id: get_user_positions(db, league.id)
        for league in leagues
    }

    db.add(ResultLog(
        match_id=match_id,
        old_goals1=match.result_goals1,
        old_goals2=match.result_goals2,
        new_goals1=goals1,
        new_goals2=goals2,
        changed_by=admin_user.id,
    ))

    match.result_goals1 = goals1
    match.result_goals2 = goals2
    match.is_finished = True
    match.finished_at = datetime.now(timezone.utc)  # used for 12h grace period in All view

    predictions = db.query(Prediction).filter(Prediction.match_id == match_id).all()
    for pred in predictions:
        pred.points = compute_points(
            pred.pred_goals1, pred.pred_goals2,
            goals1, goals2,
            pred.is_joker,
        )

    db.commit()
    db.refresh(match)

    badge_service.evaluate_badges_after_result(db, match, predictions, old_positions_by_league)
    return match
