"""
models/prob_model.py
Core probabilistic model for match outcome prediction.

Approach:
  1. Poisson Goal Expectation model (Dixon-Coles inspired)
  2. Features: Elo ratings, recent form, home advantage, head-to-head
  3. Monte Carlo simulation for uncertainty estimation
  4. Logistic Regression as baseline comparator

Outputs:
  - P(Home Win), P(Draw), P(Away Win)
  - Confidence interval via Monte Carlo
"""

import json
import math
import pickle
import numpy as np
import pandas as pd
from pathlib import Path
from typing import Optional
from scipy.stats import poisson
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, log_loss
from loguru import logger
from models.goals_model import ou_probability, btts_probability

MODEL_DIR = Path("models/cache")
MODEL_DIR.mkdir(parents=True, exist_ok=True)

ELO_K = 32          # ELO K-factor
HOME_ADVANTAGE = 100  # ELO home advantage in points


# ─── ELO Rating ───────────────────────────────────────────────────────────────
def expected_score(rating_a: float, rating_b: float, home_adv: float = HOME_ADVANTAGE) -> float:
    """Expected score for team A playing at home vs B."""
    return 1 / (1 + 10 ** ((rating_b - (rating_a + home_adv)) / 400))


def update_elo(rating_a: float, rating_b: float, score_a: float, k: float = ELO_K) -> tuple[float, float]:
    """Return updated ELO ratings after a match (score_a=1 win, 0.5 draw, 0 loss)."""
    ea = expected_score(rating_a, rating_b)
    new_a = rating_a + k * (score_a - ea)
    new_b = rating_b + k * ((1 - score_a) - (1 - ea))
    return round(new_a, 2), round(new_b, 2)


def elo_to_prob(home_elo: float, away_elo: float) -> tuple[float, float, float]:
    """
    Convert ELO difference to win/draw/loss probabilities.
    Replaced the arbitrary 27% heuristic with a principled Poisson-derived 
    draw probability based on ELO-implied lambdas.
    """
    # Map ELO difference to expected goals (lambdas)
    diff = (home_elo + HOME_ADVANTAGE) - away_elo
    # Baseline expected goals calibrated for typical ELO spreads
    lh = max(0.5, 1.35 + (diff / 400))
    la = max(0.5, 1.35 - (diff / 400))
    
    return poisson_probs(lh, la)


# ─── Poisson Model ────────────────────────────────────────────────────────────
def poisson_probs(lambda_home: float, lambda_away: float, max_goals: int = 6, rho: float = -0.10) -> tuple[float, float, float]:
    """
    Compute 1X2 probabilities from Poisson goal expectations with Dixon-Coles tau correction 
    which accounts for the dependency between low scores (boosts 0-0 and 1-1 draws).
    rho < 0 boosts draws, common empirical values are around -0.1.
    """
    home_win = draw = away_win = 0.0

    for h in range(max_goals + 1):
        for a in range(max_goals + 1):
            p = poisson.pmf(h, lambda_home) * poisson.pmf(a, lambda_away)
            
            # Dixon-Coles correction for low scores
            if h == 0 and a == 0:
                p *= max(0, 1 - lambda_home * lambda_away * rho)
            elif h == 0 and a == 1:
                p *= max(0, 1 + lambda_home * rho)
            elif h == 1 and a == 0:
                p *= max(0, 1 + lambda_away * rho)
            elif h == 1 and a == 1:
                p *= max(0, 1 - rho)

            if h > a:
                home_win += p
            elif h == a:
                draw += p
            else:
                away_win += p

    total = home_win + draw + away_win
    return (
        round(home_win / total, 4),
        round(draw / total, 4),
        round(away_win / total, 4),
    )


def estimate_lambda(
    home_attack: float, home_defence: float,
    away_attack: float, away_defence: float,
    league_avg_home: float = 1.5, league_avg_away: float = 1.2,
) -> tuple[float, float]:
    """
    Dixon-Coles lambda estimates.
    lambda_home = home_attack * away_defence * league_avg_home
    lambda_away = away_attack * home_defence * league_avg_away
    """
    lh = home_attack * away_defence * league_avg_home
    la = away_attack * home_defence * league_avg_away
    return max(lh, 0.1), max(la, 0.1)


# ─── Form parser ──────────────────────────────────────────────────────────────
def form_to_points(form_str: Optional[str]) -> float:
    """
    Convert a form string like 'W,D,L,W,W' to a 0-1 score.
    Recent results weighted more heavily.
    """
    if not form_str:
        return 0.5  # neutral
    results = [r.strip().upper() for r in form_str.split(",")][-5:]
    weights = [0.1, 0.15, 0.2, 0.25, 0.3][:len(results)]
    scores = {"W": 1.0, "D": 0.5, "L": 0.0}
    total_w = sum(weights)
    score = sum(weights[i] * scores.get(r, 0.5) for i, r in enumerate(results))
    return round(score / total_w, 4)


# ─── Feature builder ──────────────────────────────────────────────────────────
def build_features(
    home_elo: float, away_elo: float,
    home_form: Optional[str], away_form: Optional[str],
    home_injuries_count: int = 0, away_injuries_count: int = 0,
    h2h_home_wins: int = 0, h2h_draws: int = 0, h2h_away_wins: int = 0,
) -> np.ndarray:
    """
    Build feature vector for the ML model.
    Returns 1D array of shape (10,).
    """
    total_h2h = h2h_home_wins + h2h_draws + h2h_away_wins + 1e-6
    features = [
        home_elo,
        away_elo,
        home_elo - away_elo,           # ELO difference as single feature
        form_to_points(home_form),
        form_to_points(away_form),
        form_to_points(home_form) - form_to_points(away_form),
        home_injuries_count,
        away_injuries_count,
        h2h_home_wins / total_h2h,
        h2h_away_wins / total_h2h,
    ]
    return np.array(features, dtype=float)


# ─── Logistic Regression model ────────────────────────────────────────────────
class MatchPredictor:
    """Logistic regression multi-output classifier for 1X2 match prediction."""

    def __init__(self):
        self.model: Optional[LogisticRegression] = None
        self.scaler = StandardScaler()
        self._is_trained = False

    def fit(self, X: np.ndarray, y: np.ndarray):
        """Train on historical data. y: 0=Away, 1=Draw, 2=Home."""
        X_scaled = self.scaler.fit_transform(X)
        self.model = LogisticRegression(
            multi_class="multinomial", max_iter=1000, C=1.0, solver="lbfgs"
        )
        self.model.fit(X_scaled, y)
        self._is_trained = True
        acc = accuracy_score(y, self.model.predict(X_scaled))
        ll = log_loss(y, self.model.predict_proba(X_scaled))
        logger.info(f"Model trained: accuracy={acc:.3f}, log_loss={ll:.3f}")

    def predict_proba(self, x: np.ndarray) -> tuple[float, float, float]:
        """Return (home_prob, draw_prob, away_prob)."""
        if not self._is_trained:
            # Fall back to Poisson-derived probabilities from ELO + Strengths + Weather
            # This ensures the Poisson/Dixon-Coles infrastructure is used.
            home_elo, away_elo = x[0], x[1]
            
            # Map ELO/Strengths to expected goals (lambdas)
            diff = (home_elo + HOME_ADVANTAGE) - away_elo
            lh = max(0.5, 1.3 + (diff / 400))
            la = max(0.5, 1.3 - (diff / 400))
            
            # Apply weather modifiers if available
            return poisson_probs(lh, la)


        x_scaled = self.scaler.transform(x.reshape(1, -1))
        probs = self.model.predict_proba(x_scaled)[0]
        # class order: 0=Away, 1=Draw, 2=Home
        return float(probs[2]), float(probs[1]), float(probs[0])

    def predict_weighted_xg(self, 
        home_attack: float, home_defence: float,
        away_attack: float, away_defence: float,
        weather_str: str = ""
    ) -> tuple[float, float, float]:
        """
        Calculates probabilities using xG-based strengths and weather.
        """
        from automation.weather_service import get_weather_modifier
        
        lh, la = estimate_lambda(home_attack, home_defence, away_attack, away_defence)
        
        # Apply weather reduction
        reduction = get_weather_modifier(weather_str)
        lh = max(0.1, lh - reduction)
        la = max(0.1, la - reduction)
        
        return poisson_probs(lh, la)



    def save(self, path: Path = MODEL_DIR / "predictor.pkl"):
        with open(path, "wb") as f:
            pickle.dump({"model": self.model, "scaler": self.scaler, "trained": self._is_trained}, f)
        logger.info(f"Model saved to {path}")

    def load(self, path: Path = MODEL_DIR / "predictor.pkl") -> bool:
        if not path.exists():
            return False
        try:
            with open(path, "rb") as f:
                data = pickle.load(f)
            self.model = data["model"]
            self.scaler = data["scaler"]
            self._is_trained = data["trained"]
            logger.info(f"Model loaded from {path}")
            return True
        except Exception as e:
            logger.error(f"Failed to load model: {e}")
            return False


# Singleton predictor
_predictor = MatchPredictor()
_predictor.load()  # load saved model if exists


def get_predictor() -> MatchPredictor:
    return _predictor


# ─── Monte Carlo simulation ───────────────────────────────────────────────────
def monte_carlo_probs(
    home_elo: float, away_elo: float,
    home_form: Optional[str] = None, away_form: Optional[str] = None,
    n_simulations: int = 10_000, noise_std: float = 50.0,
) -> dict:
    """
    Monte Carlo simulation to get probability distributions with uncertainty.
    Returns mean probabilities and 90% confidence intervals.
    """
    home_probs, draw_probs, away_probs = [], [], []

    for _ in range(n_simulations):
        noisy_home = home_elo + np.random.normal(0, noise_std)
        noisy_away = away_elo + np.random.normal(0, noise_std)

        h, d, a = elo_to_prob(noisy_home, noisy_away)

        # Apply form adjustment ±5%
        form_adj = (form_to_points(home_form) - 0.5) * 0.1
        h = min(1, max(0, h + form_adj))
        a = min(1, max(0, a - form_adj))
        total = h + d + a
        home_probs.append(h / total)
        draw_probs.append(d / total)
        away_probs.append(a / total)

    hp, dp, ap = np.array(home_probs), np.array(draw_probs), np.array(away_probs)
    return {
        "home": {
            "mean": round(float(hp.mean()), 4),
            "ci_lower": round(float(np.percentile(hp, 5)), 4),
            "ci_upper": round(float(np.percentile(hp, 95)), 4),
        },
        "draw": {
            "mean": round(float(dp.mean()), 4),
            "ci_lower": round(float(np.percentile(dp, 5)), 4),
            "ci_upper": round(float(np.percentile(dp, 95)), 4),
        },
        "away": {
            "mean": round(float(ap.mean()), 4),
            "ci_lower": round(float(np.percentile(ap, 5)), 4),
            "ci_upper": round(float(np.percentile(ap, 95)), 4),
        },
    }

def ensemble_predict(
    home_elo: float, away_elo: float,
    home_attack: float, home_defence: float,
    away_attack: float, away_defence: float,
    home_form: Optional[str] = None,
    away_form: Optional[str] = None,
    home_match_count: int = 0,
    away_match_count: int = 0,
    weather_str: str = "",
    n_simulations: int = 2000,
    use_calibration: bool = False
) -> dict:
    """
    Blended prediction combining ELO, Dixon-Coles Poisson, and Monte Carlo.
    Weights: ELO=0.20, Dixon-Coles=0.55, Monte Carlo=0.25.

    Returns:
    {
        "home": float, "draw": float, "away": float,
        "lambda_h": float, "lambda_a": float,
        "confidence": float,
        "is_sufficient": bool,   # True if both teams have >= 10 games of history (statistically meaningful)
        "model_source": "ensemble"
    }
    """
    is_sufficient = (home_match_count >= 10 and away_match_count >= 10)
    # 1. Dixon-Coles Poisson
    lh, la = estimate_lambda(home_attack, home_defence, away_attack, away_defence)
    p_h_pois, p_d_pois, p_a_pois = poisson_probs(lh, la)

    # 2. ELO
    p_h_elo, p_d_elo, p_a_elo = elo_to_prob(home_elo, away_elo)

    # 3. Monte Carlo
    mc_res = monte_carlo_probs(home_elo, away_elo, home_form, away_form, n_simulations=n_simulations)
    p_h_mc = mc_res["home"]["mean"]
    p_d_mc = mc_res["draw"]["mean"]
    p_a_mc = mc_res["away"]["mean"]
    
    # Confidence calculation: 1 - average CI width
    ci_h = mc_res["home"]["ci_upper"] - mc_res["home"]["ci_lower"]
    ci_d = mc_res["draw"]["ci_upper"] - mc_res["draw"]["ci_lower"]
    ci_a = mc_res["away"]["ci_upper"] - mc_res["away"]["ci_lower"]
    avg_ci_width = (ci_h + ci_d + ci_a) / 3
    confidence = max(0.0, min(1.0, 1.0 - avg_ci_width))

    # 4. Blending
    p_h = (p_h_elo * 0.20) + (p_h_pois * 0.55) + (p_h_mc * 0.25)
    p_d = (p_d_elo * 0.20) + (p_d_pois * 0.55) + (p_d_mc * 0.25)
    p_a = (p_a_elo * 0.20) + (p_a_pois * 0.55) + (p_a_mc * 0.25)
    
    # Normalise
    total = p_h + p_d + p_a
    p_h, p_d, p_a = p_h / total, p_d / total, p_a / total

    # 4.5. Calibration (Platt Scaling)
    if use_calibration:
        try:
            from models.calibrator import ProbabilityCalibrator
            cal = ProbabilityCalibrator(method='logistic')
            if cal.load("epl_ensemble"):
                # Calibrator expects Away, Draw, Home order [index 0, 1, 2]
                cal_probs = cal.calibrate(np.array([p_a, p_d, p_h]))
                p_a, p_d, p_h = cal_probs[0], cal_probs[1], cal_probs[2]
                logger.debug("Applied logistic calibration to ensemble.")
        except Exception as e:
            logger.warning(f"Calibration failed: {e}")

    # 5. Secondary Markets (using lambdas)
    p_over, p_under = ou_probability(lh, la, line=2.5)
    p_btts = btts_probability(lh, la)

    return {
        "home": round(p_h, 4),
        "draw": round(p_d, 4),
        "away": round(p_a, 4),
        "lambda_h": round(lh, 4),
        "lambda_a": round(la, 4),
        "ou_over": p_over,
        "ou_under": p_under,
        "btts": p_btts,
        "confidence": round(confidence, 4),
        "is_sufficient": is_sufficient,
        "model_source": "ensemble"
    }
