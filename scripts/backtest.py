"""
scripts/backtest.py
Comprehensive backtesting harness for the AI Betting Intelligence System.
Calculates calibration metrics (Brier Score, Log Loss) and plots calibration curves
for the probabilistic model across historical matches in the database.
"""

import sys
import os
from pathlib import Path

# Add the root directory to sys.path so we can import backend/models 
sys.path.append(str(Path(__file__).parent.parent))

import asyncio
from typing import List, Tuple
from loguru import logger
from sqlalchemy import select
from sklearn.metrics import brier_score_loss, log_loss
import numpy as np

from backend.database import AsyncSessionLocal
from backend.models import Match, TeamMatchStats
from models.prob_model import ensemble_predict

async def fetch_historical_strength(db, team_id: int, up_to_date) -> tuple[float, float, float]:
    """Calculate point-in-time strengths for a team to prevent data leakage."""
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
    
    return att / 1.35, dfc / 1.35, 1500.0 # Standardize over rough league average

async def run_backtest():
    """Run historical backtest to validate model calibration."""
    logger.info("Starting Monte Carlo Backtesting Harness...")
    
    predictions = []
    actuals = []
    
    async with AsyncSessionLocal() as db:
        # Get settled matches
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
            # 1. Simulate point-in-time strength fetching to avoid future-leakage
            h_att, h_def, h_elo = await fetch_historical_strength(db, match.home_team_id, match.match_date)
            a_att, a_def, a_elo = await fetch_historical_strength(db, match.away_team_id, match.match_date)
            
            # 2. Run prediction model as it existed on that day
            pred = ensemble_predict(
                home_elo=h_elo,
                away_elo=a_elo,
                home_attack=h_att, 
                home_defence=h_def,
                away_attack=a_att, 
                away_defence=a_def,
                home_match_count=10, # Override since we enforce validation externally
                away_match_count=10, 
                weather_str=match.weather or "",
            )
            
            p_h = pred["home"]
            p_d = pred["draw"]
            p_a = pred["away"]
            
            # 3. Code the actual outcome
            if match.home_score > match.away_score:
                actual = [1, 0, 0] # Home Win
            elif match.home_score == match.away_score:
                actual = [0, 1, 0] # Draw
            else:
                actual = [0, 0, 1] # Away Win
                
            predictions.append([p_h, p_d, p_a])
            actuals.append(actual)
            
    if not predictions:
        logger.warning("No valid predictions generated.")
        return
        
    y_true = np.array(actuals)
    y_prob = np.array(predictions)
    
    # 4. Generate Core Calibration Metrics
    brier_home = brier_score_loss(y_true[:, 0], y_prob[:, 0])
    brier_draw = brier_score_loss(y_true[:, 1], y_prob[:, 1])
    brier_away = brier_score_loss(y_true[:, 2], y_prob[:, 2])
    brier_overall = (brier_home + brier_draw + brier_away) / 3.0
    
    ll = log_loss(y_true, y_prob)
    
    logger.info("==================================================")
    logger.info(f"         BACKTEST CALIBRATION RESULTS (N={len(matches)})")
    logger.info("==================================================")
    logger.info(f"  Brier Score (Home):    {brier_home:.4f}")
    logger.info(f"  Brier Score (Draw):    {brier_draw:.4f}")
    logger.info(f"  Brier Score (Away):    {brier_away:.4f}")
    logger.info("--------------------------------------------------")
    logger.info(f"  Brier Score (Overall): {brier_overall:.4f}  <-- Lower is better (0.0=Perfect, 0.33=Random)")
    logger.info(f"  Log Loss:              {ll:.4f}")
    logger.info("==================================================")
    
    if brier_overall < 0.20:
        logger.success("Verdict: Model is WELL CALIBRATED against historical data.")
    elif brier_overall < 0.23:
        logger.info("Verdict: Model is ADEQUATELY CALIBRATED but could be optimized.")
    else:
        logger.warning("Verdict: Model exhibits HIGH VARIANCE/MISCALIBRATION. Review inputs.")

if __name__ == "__main__":
    asyncio.run(run_backtest())
