import pytest
import numpy as np
from models.goals_model import (
    ou_probability,
    btts_probability,
    correct_score_distribution
)
from models.prob_model import ensemble_predict

def test_ou_probability_over_dominated():
    """lambda_h=2.5, lambda_a=2.0, line=2.5 -> p_over > 0.60"""
    p_over, p_under = ou_probability(2.5, 2.0, line=2.5)
    assert p_over > 0.60
    assert p_over + p_under == pytest.approx(1.0, rel=1e-6)

def test_ou_probability_sums_to_one():
    """p_over + p_under == 1.0 (within 1e-6)"""
    p_over, p_under = ou_probability(1.2, 0.8, line=2.5)
    assert p_over + p_under == pytest.approx(1.0, rel=1e-6)

def test_btts_high_scoring_match():
    """lambda_h=2.0, lambda_a=1.8 -> btts > 0.70"""
    prob = btts_probability(2.0, 1.8)
    assert prob > 0.70
    assert 0 <= prob <= 1.0

def test_btts_low_scoring_match():
    """lambda_h=0.7, lambda_a=0.6 -> btts < 0.40"""
    prob = btts_probability(0.7, 0.6)
    assert prob < 0.40
    assert 0 <= prob <= 1.0

def test_correct_score_sums_to_approx_one():
    """all probabilities sum to approx 1.0"""
    dist = correct_score_distribution(1.5, 1.2, max_goals=6)
    total_prob = sum(dist.values())
    assert total_prob == pytest.approx(1.0, abs=0.05)
    assert "0-0" in dist
    assert "1-1" in dist

def test_ensemble_predict_returns_all_keys():
    """verify all 9 keys present in output"""
    result = ensemble_predict(
        home_elo=1600.0, away_elo=1500.0,
        home_attack=1.2, home_defence=1.0,
        away_attack=1.0, away_defence=1.2,
        home_form="W,W,D,L,W", away_form="L,D,L,W,D",
        weather_str="Clear"
    )
    expected_keys = {
        "home", "draw", "away",
        "lambda_h", "lambda_a",
        "ou_over", "ou_under",
        "btts",
        "confidence",
        "model_source"
    }
    assert set(result.keys()) == expected_keys
    assert result["model_source"] == "ensemble"

def test_ensemble_probs_sum_to_one():
    """home + draw + away sums to 1.0 within 1e-6"""
    result = ensemble_predict(
        home_elo=1550.0, away_elo=1550.0,
        home_attack=1.1, home_defence=1.1,
        away_attack=1.1, away_defence=1.1
    )
    total = result["home"] + result["draw"] + result["away"]
    assert total == pytest.approx(1.0, rel=1e-6)
