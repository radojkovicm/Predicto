"""Unit tests for scoring_service.compute_points.

Rules:
  +10 correct outcome
  + 7 correct goal difference
  + 4 correct goals team 1
  + 4 correct goals team 2
  --- joker on top ---
  + 8 joker hit (outcome correct)
  - 5 joker miss (outcome wrong)
"""
import pytest
from app.services.scoring_service import compute_points, get_outcome, Outcome


# ---------------------------------------------------------------------------
# get_outcome
# ---------------------------------------------------------------------------

def test_outcome_home():
    assert get_outcome(2, 0) == Outcome.HOME
    assert get_outcome(1, 0) == Outcome.HOME
    assert get_outcome(99, 1) == Outcome.HOME


def test_outcome_draw():
    assert get_outcome(0, 0) == Outcome.DRAW
    assert get_outcome(1, 1) == Outcome.DRAW
    assert get_outcome(3, 3) == Outcome.DRAW


def test_outcome_away():
    assert get_outcome(0, 1) == Outcome.AWAY
    assert get_outcome(1, 3) == Outcome.AWAY
    assert get_outcome(0, 99) == Outcome.AWAY


# ---------------------------------------------------------------------------
# Base scoring — no joker
# ---------------------------------------------------------------------------

def test_perfect_score_25():
    """Exact hit: all 4 checks → 10 + 7 + 4 + 4 = 25."""
    assert compute_points(2, 1, 2, 1) == 25


def test_perfect_score_draw_0_0():
    assert compute_points(0, 0, 0, 0) == 25


def test_perfect_score_draw_2_2():
    assert compute_points(2, 2, 2, 2) == 25


def test_correct_tip_only_10():
    """Same outcome, different exact score, different GD → only +10."""
    # pred 1-0 (HOME, GD=1), res 2-0 (HOME, GD=2) — GD differs, goals differ
    assert compute_points(1, 0, 2, 0) == 10 + 4  # outcome + goals2 both 0

def test_correct_tip_home_different_goals():
    """pred 2-0, res 3-0 → outcome correct, GD differs (2 vs 3), goals2 correct."""
    assert compute_points(2, 0, 3, 0) == 10 + 4


def test_correct_gd_implies_correct_tip():
    """Same GD always implies same outcome → base 17 minimum when GD correct."""
    # pred 2-0 (HOME, GD=2), res 3-1 (HOME, GD=2)
    assert compute_points(2, 0, 3, 1) == 10 + 7


def test_correct_gd_and_goals1():
    """Same GD + correct goals for team1 only."""
    # pred 2-1 (HOME, GD=1), res 2-0 (HOME, GD=2) — GD differs
    # pred 2-0 (HOME, GD=2), res 3-1 (HOME, GD=2) — GD same, only goals2 match? no
    # Let's use pred 3-1, res 3-2: outcome HOME both, GD differs (2 vs 1), goals1 match (3)
    assert compute_points(3, 1, 3, 2) == 10 + 4


def test_correct_goals2_only():
    # pred 0-1 (AWAY), res 2-1 (HOME): outcome wrong, GD wrong, goals2 match (1)
    assert compute_points(0, 1, 2, 1) == 4


def test_correct_goals1_only():
    # pred 2-0 (HOME), res 2-3 (AWAY): outcome wrong, GD wrong (2 vs -1), goals1 match (2)
    assert compute_points(2, 0, 2, 3) == 4


def test_correct_both_goals_wrong_outcome():
    # pred 1-1 (DRAW, GD=0), res 1-1: perfect
    # Can't have both goals correct with wrong outcome — if goals match, outcome matches
    # So this case doesn't exist; test with one goal correct instead
    pass


def test_wrong_everything_0():
    # pred 3-0 (HOME), res 0-2 (AWAY): nothing matches
    assert compute_points(3, 0, 0, 2) == 0


def test_draw_correct_tip_only():
    # pred 1-1 (DRAW), res 2-2 (DRAW): outcome + GD correct, goals wrong
    assert compute_points(1, 1, 2, 2) == 10 + 7


def test_correct_outcome_and_goals2():
    # pred 0-1 (AWAY), res 1-2 (AWAY): outcome correct, GD same (both -1), goals2 wrong
    # Wait: pred GD = 0-1 = -1, res GD = 1-2 = -1: GD same → +7 too
    # goals1: 0 vs 1 wrong, goals2: 1 vs 2 wrong
    assert compute_points(0, 1, 1, 2) == 10 + 7


def test_away_correct_exact():
    assert compute_points(0, 3, 0, 3) == 25


def test_boundary_goals_zero():
    assert compute_points(0, 0, 0, 0) == 25


def test_boundary_goals_99():
    assert compute_points(99, 0, 99, 0) == 25


def test_boundary_goals_99_vs_0():
    """Max possible score margin."""
    assert compute_points(99, 0, 99, 0) == 25


# ---------------------------------------------------------------------------
# Joker
# ---------------------------------------------------------------------------

def test_joker_hit_perfect():
    """Perfect prediction + joker hit = 25 + 8 = 33."""
    assert compute_points(2, 1, 2, 1, is_joker=True) == 33


def test_joker_hit_tip_only():
    """Correct tip + joker hit: 10 + 8 = 18."""
    # pred 1-0, res 3-0: outcome HOME same, GD differs (1 vs 3), goals1 wrong, goals2 same
    assert compute_points(1, 0, 3, 0) == 10 + 4   # no joker
    assert compute_points(1, 0, 3, 0, is_joker=True) == 10 + 4 + 8


def test_joker_miss_outcome_wrong():
    """Joker on wrong outcome: −5 only."""
    # pred 1-0 (HOME), res 0-2 (AWAY): outcome wrong, GD wrong, goals wrong
    assert compute_points(1, 0, 0, 2) == 0           # no joker
    assert compute_points(1, 0, 0, 2, is_joker=True) == -5


def test_joker_miss_can_make_negative():
    """A joker miss can make total points negative."""
    pts = compute_points(1, 0, 0, 2, is_joker=True)
    assert pts < 0


def test_joker_miss_with_partial_goals():
    """Joker miss but one goal correct: 4 − 5 = −1."""
    # pred 2-1 (HOME), res 1-2 (AWAY): outcome wrong, GD wrong, goals1 wrong, goals2 wrong?
    # goals2: pred=1, res=2 — wrong
    # pred 2-0 (HOME), res 0-0 (DRAW): outcome wrong, GD wrong, goals2 same (0)
    assert compute_points(2, 0, 0, 0, is_joker=True) == 4 - 5  # goals2 correct, outcome wrong


def test_joker_false_no_penalty():
    """is_joker=False never adds/removes joker points."""
    pts_plain = compute_points(2, 1, 0, 1)
    pts_no_joker = compute_points(2, 1, 0, 1, is_joker=False)
    assert pts_plain == pts_no_joker


# ---------------------------------------------------------------------------
# Point multiplier
#
# point_multiplier scales the WHOLE match score — base + joker adjustment —
# not just the base points. i.e. total = round(multiplier * (base + joker)),
# never round(multiplier * base) + joker.
# ---------------------------------------------------------------------------

def test_multiplier_joker_hit_scales_whole_score():
    """Exact score (base=25) + joker hit (+8), x2.0: round(2.0*(25+8)) = 66.

    NOT round(2.0*25) + 8 == 58 (multiplier-on-base-only would be a bug)."""
    assert compute_points(2, 1, 2, 1, is_joker=True, point_multiplier=2.0) == 66


def test_multiplier_joker_miss_scales_whole_score():
    """base=4 (goals1 correct only) + joker miss (-5), x2.0: round(2.0*(4-5)) = -2.

    NOT round(2.0*4) - 5 == 3 (multiplier-on-base-only would be a bug)."""
    # pred 2-0 (HOME), res 2-3 (AWAY): outcome wrong, GD wrong, goals1 correct only
    assert compute_points(2, 0, 2, 3, is_joker=True, point_multiplier=2.0) == -2


def test_multiplier_no_joker_exact_multiple():
    """Non-joker, base=10 (correct tip only), x1.5: round(1.5*10) = 15, no rounding ambiguity."""
    # pred 5-1 (HOME), res 2-0 (HOME): outcome same, GD/goals both differ
    assert compute_points(5, 1, 2, 0, point_multiplier=1.5) == 15


def test_multiplier_rounding_half_to_even():
    """base=17 (tip + GD), x1.5: round(1.5*17) = round(25.5).

    Python's round() uses banker's rounding (round-half-to-even), so this is 26, not 25."""
    assert compute_points(1, 1, 2, 2, point_multiplier=1.5) == 26


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

def test_extra_time_same_as_normal():
    """Score at end of extra time is treated identically to a normal result."""
    assert compute_points(1, 1, 1, 1) == 25


def test_high_scoring_draw():
    assert compute_points(4, 4, 4, 4) == 25


def test_gd_zero_draw_vs_draw():
    # pred 0-0, res 3-3: outcome same (DRAW), GD same (0), goals wrong
    assert compute_points(0, 0, 3, 3) == 10 + 7


def test_completely_wrong_draw_prediction():
    # pred 0-0 (DRAW), res 2-0 (HOME): goals2 both 0 → only +4
    # (goals2 matching is still worth points even if outcome is wrong)
    assert compute_points(0, 0, 2, 0) == 4

def test_truly_zero_points():
    # pred 1-0 (HOME), res 0-1 (AWAY): outcome wrong, GD wrong (1 vs -1), goals1 wrong, goals2 wrong
    assert compute_points(1, 0, 0, 1) == 0
