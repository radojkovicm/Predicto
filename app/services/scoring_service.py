from dataclasses import dataclass
from enum import Enum


class Outcome(str, Enum):
    HOME = "HOME"
    DRAW = "DRAW"
    AWAY = "AWAY"


def get_outcome(goals1: int, goals2: int) -> Outcome:
    if goals1 > goals2:
        return Outcome.HOME
    elif goals1 == goals2:
        return Outcome.DRAW
    else:
        return Outcome.AWAY


@dataclass
class ScoringConfig:
    """Per-competition scoring config. Defaults reproduce WC2026's hardcoded rules."""
    points_outcome: int = 10
    points_goal_diff: int = 7
    points_goal_home: int = 4
    points_goal_away: int = 4
    joker_bonus: int = 8
    joker_penalty: int = -5


def compute_points(
    pred_goals1: int,
    pred_goals2: int,
    res_goals1: int,
    res_goals2: int,
    is_joker: bool = False,
    config: ScoringConfig = ScoringConfig(),
    point_multiplier: float = 1.0,
) -> int:
    """Compute prediction points for one match.

    Base points (max config.points_outcome + points_goal_diff + points_goal_home + points_goal_away):
      + points_outcome    correct tip (outcome match)
      + points_goal_diff  correct goal difference
      + points_goal_home  correct goals for team 1
      + points_goal_away  correct goals for team 2

    Joker bonus/penalty applied on top of base:
      + joker_bonus    if outcome correct
      + joker_penalty  if outcome wrong

    The whole match score (base + joker adjustment) is then scaled by
    point_multiplier (a phase-level multiplier, e.g. for knockout stages).
    """
    base = 0

    pred_outcome = get_outcome(pred_goals1, pred_goals2)
    res_outcome = get_outcome(res_goals1, res_goals2)

    if pred_outcome == res_outcome:
        base += config.points_outcome
    if (pred_goals1 - pred_goals2) == (res_goals1 - res_goals2):
        base += config.points_goal_diff
    if pred_goals1 == res_goals1:
        base += config.points_goal_home
    if pred_goals2 == res_goals2:
        base += config.points_goal_away

    joker_adjustment = 0
    if is_joker:
        if pred_outcome == res_outcome:
            joker_adjustment = config.joker_bonus
        else:
            joker_adjustment = config.joker_penalty

    return round(point_multiplier * (base + joker_adjustment))
