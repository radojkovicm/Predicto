"""Badge evaluation — called after every result entry.

Personal badges (league_id=None):  prophet, hot_streak, joker_master, joker_victim, iron_man
League badges   (league_id=X):     lone_wolf, sheep, comeback_king, group_stage_guru

Badge lifecycle:
- Badges are awarded when conditions are met
- Old badges (> BADGE_LIFETIME_DAYS) are deactivated (not deleted, preserved in audit trail)
- Only active badges are displayed to users
"""
from collections import Counter
from typing import Optional
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.models.models import League, Match, Prediction, User, UserBadge, UserLeague
from app.services.scoring_service import get_outcome, Outcome

# How many days a badge remains active before being deactivated
# (3 days = ~10 matches cycle)
BADGE_LIFETIME_DAYS = 3

# Hot Streak: this many consecutive matches, each worth at least this many points
HOT_STREAK_MIN_POINTS = 17
HOT_STREAK_LENGTH = 4

BADGE_META = {
    "prophet":          ("Prophet",          "🔮"),
    "hot_streak":       ("Hot Streak",        "🔥"),
    "joker_master":     ("Joker Master",      "🃏"),
    "joker_victim":     ("Joker Victim",      "💀"),
    "lone_wolf":        ("Lone Wolf",         "🐺"),
    "sheep":            ("Sheep",             "🐑"),
    "comeback_king":    ("Comeback King",     "👑"),
    "iron_man":         ("Iron Man",          "💪"),
    "group_stage_guru": ("Group Stage Guru",  "🏆"),
}


def badge_display(code: str) -> tuple[str, str]:
    return BADGE_META.get(code, (code, "🏅"))


def _award(
    db: Session,
    user_id: int,
    badge_code: str,
    competition_id: int,
    match_id: Optional[int] = None,
    league_id: Optional[int] = None,
) -> bool:
    """Award a badge idempotently. Returns True if newly awarded."""
    existing = (
        db.query(UserBadge)
        .filter(
            UserBadge.user_id == user_id,
            UserBadge.badge_code == badge_code,
            UserBadge.match_id == match_id,
            UserBadge.league_id == league_id,
            UserBadge.competition_id == competition_id,
        )
        .first()
    )
    if existing:
        return False
    db.add(UserBadge(user_id=user_id, badge_code=badge_code,
                     match_id=match_id, league_id=league_id,
                     competition_id=competition_id))
    db.flush()
    return True


# ---------------------------------------------------------------------------
# Main entry point called from result_service
# ---------------------------------------------------------------------------

def _deactivate_old_badges(db: Session) -> None:
    """Deactivate badges older than BADGE_LIFETIME_DAYS (default: 4 days).
    
    This keeps the audit trail intact while removing old badges from display.
    """
    cutoff_date = datetime.utcnow() - timedelta(days=BADGE_LIFETIME_DAYS)
    old_badges = (
        db.query(UserBadge)
        .filter(
            UserBadge.is_active == True,
            UserBadge.awarded_at < cutoff_date,
        )
        .all()
    )
    for badge in old_badges:
        badge.is_active = False
    if old_badges:
        db.flush()


def evaluate_badges_after_result(
    db: Session,
    match: Match,
    predictions: list[Prediction],
    old_positions_by_league: dict[int, dict[int, int]],
) -> None:
    # Deactivate old badges before awarding new ones
    _deactivate_old_badges(db)
    
    res1 = match.result_goals1
    res2 = match.result_goals2
    if res1 is None or res2 is None:
        return

    res_outcome = get_outcome(res1, res2)
    competition_id = match.competition_id

    # ── 1. Personal badges (no league context) ──────────────────────────────
    for pred in predictions:
        pred_outcome = get_outcome(pred.pred_goals1, pred.pred_goals2)
        if pred.pred_goals1 == res1 and pred.pred_goals2 == res2:
            _award(db, pred.user_id, "prophet", competition_id, match.id)
        if pred.is_joker:
            if pred_outcome == res_outcome:
                _award(db, pred.user_id, "joker_master", competition_id, match.id)
            else:
                _award(db, pred.user_id, "joker_victim", competition_id, match.id)

    user_ids = {p.user_id for p in predictions}
    for uid in user_ids:
        _check_hot_streak(db, uid, competition_id)

    _check_iron_man(db, match, competition_id)

    # ── 2. League-scoped comparison badges ───────────────────────────────────
    leagues = db.query(League).filter(League.competition_id == competition_id).all()
    for league in leagues:
        member_ids = {
            r.user_id
            for r in db.query(UserLeague.user_id)
            .filter(UserLeague.league_id == league.id)
            .all()
        }
        league_preds = [p for p in predictions if p.user_id in member_ids]
        if not league_preds:
            continue

        total = len(league_preds)
        correct_preds = [
            p for p in league_preds
            if get_outcome(p.pred_goals1, p.pred_goals2) == res_outcome
        ]
        wrong_count = total - len(correct_preds)
        wrong_pct = wrong_count / total

        # lone_wolf
        if wrong_pct >= 0.70 and len(correct_preds) <= 1:
            for p in correct_preds:
                _award(db, p.user_id, "lone_wolf", competition_id, match.id, league.id)

        # sheep — majority was wrong, and you were in that majority
        if wrong_pct > 0.5:
            outcome_counts = Counter(
                get_outcome(p.pred_goals1, p.pred_goals2).value
                for p in league_preds
            )
            majority_outcome = max(outcome_counts, key=outcome_counts.__getitem__)
            for p in league_preds:
                pred_oc = get_outcome(p.pred_goals1, p.pred_goals2)
                if pred_oc.value == majority_outcome and pred_oc != res_outcome:
                    _award(db, p.user_id, "sheep", competition_id, match.id, league.id)

        # comeback_king
        from app.services.ranking_service import get_user_positions
        old_pos = old_positions_by_league.get(league.id, {})
        new_pos = get_user_positions(db, league.id)
        for uid, old_rank in old_pos.items():
            if uid not in member_ids:
                continue
            new_rank = new_pos.get(uid, old_rank)
            if old_rank - new_rank >= 5:
                _award(db, uid, "comeback_king", competition_id, None, league.id)

        # group_stage_guru
        _check_group_stage_guru(db, league.id, competition_id)

    db.commit()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _check_hot_streak(db: Session, user_id: int, competition_id: int) -> None:
    finished_preds = (
        db.query(Prediction)
        .join(Match, Prediction.match_id == Match.id)
        .filter(
            Prediction.user_id == user_id,
            Match.competition_id == competition_id,
            Match.is_finished == True,
            Prediction.points.isnot(None),
        )
        .order_by(Match.kickoff_utc)
        .all()
    )
    if len(finished_preds) < HOT_STREAK_LENGTH:
        return
    for i in range(len(finished_preds) - HOT_STREAK_LENGTH + 1):
        window = finished_preds[i: i + HOT_STREAK_LENGTH]
        if all(p.points >= HOT_STREAK_MIN_POINTS for p in window):
            _award(db, user_id, "hot_streak", competition_id)
            return


def _check_iron_man(db: Session, match: Match, competition_id: int) -> None:
    phase_matches = db.query(Match).filter(Match.phase_id == match.phase_id).all()
    if not all(m.is_finished for m in phase_matches):
        return
    match_ids = {m.id for m in phase_matches}
    match_count = len(match_ids)

    pred_counts = dict(
        db.query(Prediction.user_id, func.count(Prediction.id))
        .filter(Prediction.match_id.in_(match_ids))
        .group_by(Prediction.user_id)
        .all()
    )
    for user in db.query(User).all():
        if pred_counts.get(user.id, 0) == match_count:
            _award(db, user.id, "iron_man", competition_id)


def _check_group_stage_guru(db: Session, league_id: int, competition_id: int) -> None:
    from app.models.models import Phase
    group_phases = (
        db.query(Phase)
        .filter(
            Phase.competition_id == competition_id,
            Phase.is_group_stage == True,
        )
        .all()
    )
    if not group_phases:
        return
    phase_ids = {p.id for p in group_phases}
    group_matches = db.query(Match).filter(Match.phase_id.in_(phase_ids)).all()
    if not all(m.is_finished for m in group_matches):
        return

    member_ids = [
        r.user_id
        for r in db.query(UserLeague.user_id).filter(UserLeague.league_id == league_id).all()
    ]
    if not member_ids:
        return

    user_points = (
        db.query(Prediction.user_id, func.sum(Prediction.points).label("pts"))
        .join(Match, Prediction.match_id == Match.id)
        .filter(
            Match.phase_id.in_(phase_ids),
            Prediction.points.isnot(None),
            Prediction.user_id.in_(member_ids),
        )
        .group_by(Prediction.user_id)
        .order_by(func.sum(Prediction.points).desc())
        .all()
    )
    if not user_points:
        return
    top_pts = user_points[0].pts
    for row in user_points:
        if row.pts == top_pts:
            _award(db, row.user_id, "group_stage_guru", competition_id, None, league_id)
        else:
            break
