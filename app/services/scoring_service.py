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


def compute_points(
    pred_goals1: int,
    pred_goals2: int,
    res_goals1: int,
    res_goals2: int,
    is_joker: bool = False,
) -> int:
    """Compute prediction points for one match.

    Base points (max 25):
      +10  correct tip (outcome match)
      + 7  correct goal difference
      + 4  correct goals for team 1
      + 4  correct goals for team 2

    Joker bonus/penalty applied on top of base:
      + 8  if outcome correct
      - 5  if outcome wrong
    """
    points = 0

    pred_outcome = get_outcome(pred_goals1, pred_goals2)
    res_outcome = get_outcome(res_goals1, res_goals2)

    if pred_outcome == res_outcome:
        points += 10
    if (pred_goals1 - pred_goals2) == (res_goals1 - res_goals2):
        points += 7
    if pred_goals1 == res_goals1:
        points += 4
    if pred_goals2 == res_goals2:
        points += 4

    if is_joker:
        if pred_outcome == res_outcome:
            points += 8
        else:
            points -= 5

    return points
