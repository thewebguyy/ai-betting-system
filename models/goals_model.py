"""
models/goals_model.py
Probability calculations for alternative markets (O/U, BTTS, Correct Score).
"""

from typing import Optional
from scipy.stats import poisson
from loguru import logger

def ou_probability(lambda_h: float, lambda_a: float, line: float = 2.5,
                   max_goals: int = 10) -> tuple[float, float]:
    """
    Returns (p_over, p_under) using bivariate Poisson PMF.
    Sum all (h,a) pairs where h+a > line for p_over.
    """
    p_over = 0.0
    for h in range(max_goals + 1):
        for a in range(max_goals + 1):
            prob = poisson.pmf(h, lambda_h) * poisson.pmf(a, lambda_a)
            if h + a > line:
                p_over += prob
    
    p_under = 1.0 - p_over
    return round(float(p_over), 4), round(float(p_under), 4)

def btts_probability(lambda_h: float, lambda_a: float) -> float:
    """
    P(BTTS) = P(home scores >= 1) * P(away scores >= 1)
    = (1 - poisson.pmf(0, lambda_h)) * (1 - poisson.pmf(0, lambda_a))
    """
    p_h_scores = 1.0 - poisson.pmf(0, lambda_h)
    p_a_scores = 1.0 - poisson.pmf(0, lambda_a)
    return round(float(p_h_scores * p_a_scores), 4)

def correct_score_distribution(lambda_h: float, lambda_a: float,
                                max_goals: int = 6) -> dict[str, float]:
    """
    Returns dict of {"0-0": prob, "1-0": prob, "0-1": prob, ...} for all
    (h, a) combinations up to max_goals x max_goals.
    Keys are "{home_goals}-{away_goals}" strings.
    """
    distribution = {}
    for h in range(max_goals + 1):
        for a in range(max_goals + 1):
            prob = poisson.pmf(h, lambda_h) * poisson.pmf(a, lambda_a)
            distribution[f"{h}-{a}"] = round(float(prob), 4)
    return distribution
