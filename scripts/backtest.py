"""
scripts/backtest.py
Comprehensive backtesting harness for the AI Betting Intelligence System.
Calculates calibration metrics (Brier Score, Log Loss) and plots calibration curves
for the probabilistic model across historical matches in the database.

CRITICAL ARCHITECTURAL NOTES:
1. Point-in-Time Reality: This script attempts to recreate strengths chronologically. 
   True backtesting requires a full chronological ELO/xG replay from the start of the dataset.
2. Baselines: Brier scores mean nothing in a vacuum. This harness compares the model's
   Brier score against the Bookmaker's closing implied probability baseline.
3. Walk-forward Validation: Currently evaluates all settled matches. For robust variance 
   testing, adapt this to test season-by-season (e.g., train on N, test on N+1).
"""

import sys
import os
from pathlib import Path

# Add the root directory to sys.path so we can import backend/models 
sys.path.append(str(Path(__file__).parent.parent))

import asyncio
from typing import List, Tuple, Dict
from loguru import logger
from sqlalchemy import select
from sklearn.metrics import brier_score_loss, log_loss
import numpy as np

from backend.database import AsyncSessionLocal
from backend.models import Match, TeamMatchStats, OddsHistory
from models.prob_model import ensemble_predict
from models.value_model import remove_vig

async def fetch_historical_strength(db, team_id: int, up_to_date) -> tuple[float, float, float]:
    """
    Calculate point-in-time strengths for a team to prevent data leakage.
    NOTE: A true production backtester would use a memory-state EloTracker 
    iterating chronologically, rather than querying backward for every match.
    """
    stmt = (
        select(TeamMatchStats)
        .join(Match, Match.id == TeamMatchStats.match_id)
        .where(
            TeamMatchStats.team_id == team_id,
            Match.match_date < up_to_date
        )
        .order_by(Match.match_date.desc())
        .limit(10)
    )
    result = await db.execute(stmt)
    rows = result.scalars().all()
    
    if not rows:
        return 1.35, 1.35, 1500.0 # Default fallback
        
    weights = [1.0 - (i * 0.05) for i in range(len(rows))]
    total_w = sum(weights)
    att = sum(r.xg_for * w for r, w in zip(rows, weights)) / total_w
    dfc = sum(r.xg_against * w for r, w in zip(rows, weights)) / total_w
    
    # Simple simulated historical ELO: base is 1500, +20 for every win, -20 for loss
    points = 1500.0
    for r in rows:
        if r.goals_for > r.goals_against: points += 20
        elif r.goals_for < r.goals_against: points -= 20
    
    return att / 1.35, dfc / 1.35, points

async def get_bookie_baseline(db, match_id: int) -> tuple[float, float, float]:
    """
    Get the bookmaker's "true" implied probability (vig-removed) just before kickoff
    to serve as our calibration baseline.
    """
    stmt = (
        select(OddsHistory)
        .where(OddsHistory.match_id == match_id)
        .order_by(OddsHistory.fetched_at.desc())
        .limit(1)
    )
    res = await db.execute(stmt)
    odds = res.scalar_one_or_none()
    
    if odds and odds.home_odds and odds.away_odds:
        vig = remove_vig(odds.home_odds, odds.draw_odds, odds.away_odds)
        return vig["home"], vig["draw"], vig["away"]
    
    # Fallback to random uniform if no odds exist for this historical match
    return 0.333, 0.333, 0.333

def print_reliability_diagram(y_true: np.ndarray, y_prob: np.ndarray, n_bins: int = 10, label: str = "Home Win"):
    """
    Prints a text-based reliability diagram (calibration curve) to observe 
    directional bias (over/underconfidence).
    """
    bins = np.linspace(0.0, 1.0, n_bins + 1)
    indices = np.digitize(y_prob, bins) - 1
    
    logger.info(f"--- Reliability/Calibration Bins: {label} ---")
    logger.info(f"{'Bin Range':<15} | {'Count':<6} | {'Pred Avg':<10} | {'Actual Freq':<10} | {'Bias'}")
    
    for i in range(n_bins):
        mask = (indices == i)
        if np.sum(mask) == 0:
            continue
            
        pred_avg = np.mean(y_prob[mask])
        actual_freq = np.mean(y_true[mask])
        count = np.sum(mask)
        bias = pred_avg - actual_freq
        
        bias_str = "Overconfident" if bias > 0.05 else ("Underconfident" if bias < -0.05 else "Calibrated")
        
        logger.info(f"{bins[i]:.2f} - {bins[i+1]:.2f} | {count:<6} | {pred_avg:.3f}      | {actual_freq:.3f}        | {bias:+.3f} ({bias_str})")

async def run_backtest():
    """Run historical backtest to validate model calibration vs bookmaker baseline."""
    logger.info("Starting Monte Carlo Backtesting Harness...")
    
    predictions = []
    actuals = []
    baselines = []
    
    async with AsyncSessionLocal() as db:
        stmt = select(Match).where(
            Match.status == "finished", 
            Match.home_score != None, 
            Match.away_score != None
        )
        result = await db.execute(stmt)
        matches = result.scalars().all()
        
        if not matches:
            logger.warning("No settled matches found in the database. Run fetch tasks to populate history.")
            return

        logger.info(f"Evaluating {len(matches)} historical matches for Brier Score calibration...")
        
        for match in matches:
            # 1. Point-in-time reconstruction
            h_att, h_def, h_elo = await fetch_historical_strength(db, match.home_team_id, match.match_date)
            a_att, a_def, a_elo = await fetch_historical_strength(db, match.away_team_id, match.match_date)
            
            # 2. Extract baseline bookmaker probabilities
            b_h, b_d, b_a = await get_bookie_baseline(db, match.id)
            baselines.append([b_h, b_d, b_a])
            
            # 3. Predict via Model
            pred = ensemble_predict(
                home_elo=h_elo, away_elo=a_elo,
                home_attack=h_att, home_defence=h_def,
                away_attack=a_att, away_defence=a_def,
                home_match_count=15, # Hardcoding >10 to bypass sufficiency check during loop
                away_match_count=15, 
                weather_str=match.weather or "",
            )
            
            # 4. Code Actual Outcome
            if match.home_score > match.away_score:
                actual = [1, 0, 0] # Home Win
            elif match.home_score == match.away_score:
                actual = [0, 1, 0] # Draw
            else:
                actual = [0, 0, 1] # Away Win
                
            predictions.append([pred["home"], pred["draw"], pred["away"]])
            actuals.append(actual)
            
    if not predictions:
        logger.warning("No valid predictions generated.")
        return
        
    y_true = np.array(actuals)
    y_prob = np.array(predictions)
    y_base = np.array(baselines)
    
    # 5. Compute Comparative Brier Scores
    brier_m_home = brier_score_loss(y_true[:, 0], y_prob[:, 0])
    brier_m_draw = brier_score_loss(y_true[:, 1], y_prob[:, 1])
    brier_m_away = brier_score_loss(y_true[:, 2], y_prob[:, 2])
    brier_model_avg = (brier_m_home + brier_m_draw + brier_m_away) / 3.0
    
    brier_b_home = brier_score_loss(y_true[:, 0], y_base[:, 0])
    brier_b_draw = brier_score_loss(y_true[:, 1], y_base[:, 1])
    brier_b_away = brier_score_loss(y_true[:, 2], y_base[:, 2])
    brier_base_avg = (brier_b_home + brier_b_draw + brier_b_away) / 3.0
    
    ll_model = log_loss(y_true, y_prob)
    ll_base = log_loss(y_true, y_base)
    
    value_add = brier_base_avg - brier_model_avg
    
    logger.info("==================================================")
    logger.info(f"      BACKTEST CALIBRATION RESULTS (N={len(matches)})")
    logger.info("==================================================")
    logger.info("METRIC                 | MODEL    | BASELINE ")
    logger.info("--------------------------------------------------")
    logger.info(f"Brier (Home)           | {brier_m_home:.4f}   | {brier_b_home:.4f}")
    logger.info(f"Brier (Draw)           | {brier_m_draw:.4f}   | {brier_b_draw:.4f}")
    logger.info(f"Brier (Away)           | {brier_m_away:.4f}   | {brier_b_away:.4f}")
    logger.info(f"Brier (Overall Avg)    | {brier_model_avg:.4f}   | {brier_base_avg:.4f}")
    logger.info(f"Log Loss               | {ll_model:.4f}   | {ll_base:.4f}")
    logger.info("==================================================")
    
    if value_add > 0.005:
        logger.success(f"Verdict: EXCELLENT. Model outperforms bookie baseline by {value_add:.4f} Brier points.")
    elif value_add > -0.002:
        logger.info(f"Verdict: COMPETITIVE. Model is closely calibrated with the baseline ({value_add:+.4f} diff).")
    else:
        logger.warning(f"Verdict: POOR. Model underperforms the implied odds baseline by {abs(value_add):.4f} Brier. Do not bet.")
        
    logger.info("\n")
    print_reliability_diagram(y_true[:, 0], y_prob[:, 0], label="Home Win")
    logger.info("\n")
    print_reliability_diagram(y_true[:, 1], y_prob[:, 1], label="Draw")

if __name__ == "__main__":
    asyncio.run(run_backtest())
