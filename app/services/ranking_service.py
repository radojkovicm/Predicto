from sqlalchemy.orm import Session
from sqlalchemy import func, case, and_, or_, text

from app.models.models import User, Prediction, Match, UserBadge, UserLeague, League


def get_leaderboard(db: Session, league_id: int) -> list[dict]:
    """Return ranked leaderboard for members of the given league only.

    Tie-break:
      1. Total points DESC
      2. Correct tips DESC
      3. Correct exact scores DESC
      4. MAX(updated_at) ASC — earliest last prediction
    """
    league = db.query(League).get(league_id)
    if league is None:
        return []

    member_ids = [
        r.user_id
        for r in db.query(UserLeague.user_id).filter(UserLeague.league_id == league_id).all()
    ]
    if not member_ids:
        return []

    # A user may have predictions from other leagues/competitions too;
    # every aggregate below is guarded by this so only this league's
    # competition contributes. The outer joins are untouched, so
    # zero-prediction members still show up (Match is NULL -> guard is
    # NULL/false there, and coalesce() below still yields 0).
    in_competition = Match.competition_id == league.competition_id

    correct_tip_cond = and_(
        in_competition,
        Match.is_finished,
        or_(
            and_(Prediction.pred_goals1 > Prediction.pred_goals2,
                 Match.result_goals1 > Match.result_goals2),
            and_(Prediction.pred_goals1 == Prediction.pred_goals2,
                 Match.result_goals1 == Match.result_goals2),
            and_(Prediction.pred_goals1 < Prediction.pred_goals2,
                 Match.result_goals1 < Match.result_goals2),
        ),
    )
    exact_score_cond = and_(
        in_competition,
        Match.is_finished,
        Prediction.pred_goals1 == Match.result_goals1,
        Prediction.pred_goals2 == Match.result_goals2,
    )

    rows = (
        db.query(
            User.id.label("user_id"),
            User.username,
            User.first_name,
            User.last_name,
            func.coalesce(
                func.sum(case((in_competition, Prediction.points), else_=0)), 0
            ).label("total_points"),
            func.count(case((correct_tip_cond, 1), else_=None)).label("correct_tips"),
            func.count(case((exact_score_cond, 1), else_=None)).label("exact_scores"),
            func.max(case((in_competition, Prediction.updated_at), else_=None)).label("last_pred_at"),
        )
        .filter(User.id.in_(member_ids))
        .outerjoin(Prediction, User.id == Prediction.user_id)
        .outerjoin(Match, Prediction.match_id == Match.id)
        .group_by(User.id, User.username)
        .order_by(
            text("total_points DESC"),
            text("correct_tips DESC"),
            text("exact_scores DESC"),
            text("last_pred_at ASC NULLS LAST"),
        )
        .all()
    )

    # Badges: personal (league_id IS NULL) + this league's badges
    # Filter to show only ACTIVE badges
    all_badges = (
        db.query(UserBadge.user_id, UserBadge.badge_code)
        .filter(
            UserBadge.user_id.in_(member_ids),
            UserBadge.is_active == True,
            UserBadge.competition_id == league.competition_id,
            or_(UserBadge.league_id == league_id, UserBadge.league_id == None),
        )
        .all()
    )
    badges_by_user: dict[int, list[str]] = {}
    for ub in all_badges:
        badges_by_user.setdefault(ub.user_id, []).append(ub.badge_code)

    leaderboard = []
    for rank, row in enumerate(rows, start=1):
        full = f"{row.first_name or ''} {row.last_name or ''}".strip()
        leaderboard.append(
            {
                "rank": rank,
                "user_id": row.user_id,
                "username": row.username,
                "display_name": full if full else row.username,
                "total_points": int(row.total_points),
                "correct_tips": int(row.correct_tips),
                "exact_scores": int(row.exact_scores),
                "last_pred_at": row.last_pred_at,
                "badges": list(dict.fromkeys(badges_by_user.get(row.user_id, []))),
            }
        )
    return leaderboard


def get_user_positions(db: Session, league_id: int) -> dict[int, int]:
    return {e["user_id"]: e["rank"] for e in get_leaderboard(db, league_id)}
