from collections import Counter
from typing import Optional
from sqlalchemy.orm import Session, joinedload

from app.models.models import Match, Prediction, UserLeague
from app.services.scoring_service import get_outcome, Outcome


def get_match_stats(db: Session, match_id: int, league_id: Optional[int] = None) -> dict:
    """Per-match prediction statistics, optionally filtered to league members."""
    match = db.query(Match).filter(Match.id == match_id).first()
    if not match:
        return {}

    query = (
        db.query(Prediction)
        .options(joinedload(Prediction.user))
        .filter(Prediction.match_id == match_id)
    )
    if league_id is not None:
        member_ids = [
            r.user_id
            for r in db.query(UserLeague.user_id).filter(UserLeague.league_id == league_id).all()
        ]
        query = query.filter(Prediction.user_id.in_(member_ids))

    predictions = query.all()
    total = len(predictions)

    if total == 0:
        return {
            "total": 0,
            "home_count": 0, "draw_count": 0, "away_count": 0,
            "home_pct": 0, "draw_pct": 0, "away_pct": 0,
            "most_common_score": None,
            "correct_tips": 0, "wrong_tips": 0,
            "prophets": [], "all_predictions": [],
        }

    home_count = sum(1 for p in predictions if get_outcome(p.pred_goals1, p.pred_goals2) == Outcome.HOME)
    draw_count = sum(1 for p in predictions if get_outcome(p.pred_goals1, p.pred_goals2) == Outcome.DRAW)
    away_count = total - home_count - draw_count

    score_counter = Counter(f"{p.pred_goals1}:{p.pred_goals2}" for p in predictions)
    most_common_score = score_counter.most_common(1)[0][0] if score_counter else None

    stats: dict = {
        "total": total,
        "home_count": home_count, "draw_count": draw_count, "away_count": away_count,
        "home_pct": round(home_count / total * 100),
        "draw_pct": round(draw_count / total * 100),
        "away_pct": round(away_count / total * 100),
        "most_common_score": most_common_score,
        "correct_tips": 0, "wrong_tips": 0, "prophets": [],
    }

    if match.is_finished and match.result_goals1 is not None:
        res_outcome = get_outcome(match.result_goals1, match.result_goals2)
        correct = sum(1 for p in predictions
                      if get_outcome(p.pred_goals1, p.pred_goals2) == res_outcome)
        prophets = [
            p.user.display_name for p in predictions
            if p.pred_goals1 == match.result_goals1 and p.pred_goals2 == match.result_goals2
        ]
        stats["correct_tips"] = correct
        stats["wrong_tips"] = total - correct
        stats["prophets"] = prophets

    stats["all_predictions"] = [
        {
            "display_name": p.user.display_name,
            "pred": f"{p.pred_goals1}:{p.pred_goals2}",
            "is_joker": p.is_joker,
            "points": p.points,
            "outcome": get_outcome(p.pred_goals1, p.pred_goals2).value,
        }
        for p in sorted(predictions, key=lambda p: p.user.display_name)
    ]
    return stats
