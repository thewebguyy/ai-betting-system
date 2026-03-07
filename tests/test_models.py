"""
tests/test_models.py
Unit tests for core probability and value evaluation logic.
"""

import pytest
from models.prob_model import elo_to_prob, expected_score, estimate_lambda, poisson_probs
from models.value_model import implied_probability, remove_vig, expected_value, kelly_criterion

# ─── ELO & Prob Model Tests ───────────────────────────────────────────────────

def test_expected_score():
    # Equal ratings with home advantage
    score = expected_score(1500, 1500, home_adv=100)
    assert score > 0.5  # Home should be favored
    assert round(score, 2) == 0.64

    # Equal ratings, no home advantage
    score_neutral = expected_score(1500, 1500, home_adv=0)
    assert score_neutral == 0.5

def test_elo_to_prob():
    h, d, a = elo_to_prob(1600, 1500)
    assert h > a  # higher ELO + home advantage = strongly favored home
    assert round(h + d + a, 4) == 1.0

def test_estimate_lambda():
    lh, la = estimate_lambda(
        home_attack=1.1, home_defence=0.9,
        away_attack=0.8, away_defence=1.2,
        league_avg_home=1.5, league_avg_away=1.2
    )
    assert lh > la
    assert lh == 1.1 * 1.2 * 1.5
    assert la == 0.8 * 0.9 * 1.2

def test_poisson_probs():
    h_prob, d_prob, a_prob = poisson_probs(2.0, 1.0)
    assert h_prob > a_prob
    assert round(h_prob + d_prob + a_prob, 2) <= 1.0  # capped at max_goals

# ─── Value Model Tests ────────────────────────────────────────────────────────

def test_implied_probability():
    assert implied_probability(2.0) == 0.5
    assert implied_probability(5.0) == 0.2
    assert implied_probability(1.5) == round(1/1.5, 6)

def test_remove_vig():
    # Odds with typical vig
    res = remove_vig(2.0, 3.2, 3.8)
    # Implied: 0.5, 0.3125, 0.2631 -> sum = 1.0756
    assert res["overround"] > 0
    assert res["vig_pct"] > 0
    assert round(res["home"] + res["draw"] + res["away"], 4) == 1.0
    assert res["home"] < 0.5  # raw implied was 0.5, true must be lower

def test_expected_value():
    ev_pos = expected_value(model_prob=0.55, decimal_odds=2.0)
    # EV = 0.55 * 1 - 0.45 = 0.10
    assert round(ev_pos, 2) == 0.10

    ev_neg = expected_value(model_prob=0.45, decimal_odds=2.0)
    # EV = 0.45 * 1 - 0.55 = -0.10
    assert round(ev_neg, 2) == -0.10

def test_kelly_criterion():
    kf = kelly_criterion(model_prob=0.55, decimal_odds=2.0)
    # b = 1; p = 0.55; q = 0.45
    # f = (1*0.55 - 0.45)/1 = 0.10
    assert round(kf, 2) == 0.10

    # Negative EV should return 0 Kelly
    kf_neg = kelly_criterion(model_prob=0.45, decimal_odds=2.0)
    assert kf_neg == 0.0
