import sys
import os
from pathlib import Path
import json
from collections import defaultdict

# Add the root directory to sys.path so we can import backend/models 
sys.path.append(str(Path(__file__).parent.parent))

import asyncio
from typing import List, Tuple, Dict
from loguru import logger
from sqlalchemy import select, func
from sqlalchemy.orm import joinedload
from sklearn.metrics import brier_score_loss, log_loss
import numpy as np

from backend.database import AsyncSessionLocal
from backend.models import Match, TeamMatchStats, OddsHistory, League
from models.prob_model import ensemble_predict
from models.value_model import remove_vig

async def fetch_historical_strength(db, team_id: int, up_to_date) -> tuple[float, float, float, int]:
    """
    Calculate point-in-time strengths for a team to prevent data leakage.
    Returns (attack_strength, defence_strength, elo, match_count).
    """
    # Get TOTAL count of historical matches for this team before the date
    count_stmt = (
        select(func.count(TeamMatchStats.id))
        .join(Match, Match.id == TeamMatchStats.match_id)
        .where(
            TeamMatchStats.team_id == team_id,
            Match.match_date < up_to_date
        )
    )
    count_res = await db.execute(count_stmt)
    total_count = count_res.scalar() or 0

    # Get last 10 for strengths calculation
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
        return 1.35, 1.35, 1500.0, 0
        
    weights = [1.0 - (i * 0.05) for i in range(len(rows))]
    total_w = sum(weights)
    att = sum(r.xg_for * w for r, w in zip(rows, weights)) / total_w
    dfc = sum(r.xg_against * w for r, w in zip(rows, weights)) / total_w
    
    # Simple simulated historical ELO: base is 1500, +20 for every win, -20 for loss
    points = 1500.0
    for r in rows:
        if r.goals_for > r.goals_against: points += 20
        elif r.goals_for < r.goals_against: points -= 20
    
    return att / 1.35, dfc / 1.35, points, total_count

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
    Prints a text-based reliability diagram (calibration curve).
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
    """Run historical backtest with live parity enforcement."""
    logger.info("Starting Measurement-First Backtesting Harness...")
    
    stats = {
        "total_processed": 0,
        "total_skipped": 0,
        "total_predictions": 0,
        "league_breakdown": defaultdict(lambda: {"processed": 0, "skipped": 0, "predicted": 0})
    }
    
    predictions = []
    actuals = []
    baselines = []
    
    async with AsyncSessionLocal() as db:
        stmt = select(Match).options(joinedload(Match.league)).where(
            Match.status == "finished", 
            Match.home_score != None, 
            Match.away_score != None
        )
        result = await db.execute(stmt)
        matches = result.scalars().all()
        
        if not matches:
            logger.warning("No settled matches found in the database.")
            return

        logger.info(f"Analyzing {len(matches)} historical matches...")
        
        for match in matches:
            stats["total_processed"] += 1
            league_name = match.league.name if match.league else "Unknown"
            stats["league_breakdown"][league_name]["processed"] += 1
            
            # 1. Point-in-time reconstruction
            h_att, h_def, h_elo, h_count = await fetch_historical_strength(db, match.home_team_id, match.match_date)
            a_att, a_def, a_elo, a_count = await fetch_historical_strength(db, match.away_team_id, match.match_date)
            
            # 2. Enforce sufficiency parity
            # Live logic: home_match_count >= 10 and away_match_count >= 10
            pred = ensemble_predict(
                home_elo=h_elo, away_elo=a_elo,
                home_attack=h_att, home_defence=h_def,
                away_attack=a_att, away_defence=a_def,
                home_match_count=h_count,
                away_match_count=a_count, 
                weather_str=match.weather or "",
            )
            
            if not pred.get("is_sufficient"):
                stats["total_skipped"] += 1
                stats["league_breakdown"][league_name]["skipped"] += 1
                logger.debug(f"Skipping match_id={match.id} ({league_name}): insufficient_data (H={h_count}, A={a_count})")
                continue

            stats["total_predictions"] += 1
            stats["league_breakdown"][league_name]["predicted"] += 1
            
            # 3. Extract baseline bookmaker probabilities
            b_h, b_d, b_a = await get_bookie_baseline(db, match.id)
            baselines.append([b_h, b_d, b_a])
            
            # 4. Code Actual Outcome
            if match.home_score > match.away_score:
                actual = [1, 0, 0]
            elif match.home_score == match.away_score:
                actual = [0, 1, 0]
            else:
                actual = [0, 0, 1]
                
            predictions.append([pred["home"], pred["draw"], pred["away"]])
            actuals.append(actual)
            
    # Output Summary Report
    logger.info("==================================================")
    logger.info("      BACKTEST EXECUTION SUMMARY")
    logger.info("==================================================")
    logger.info(f"Total Matches Processed: {stats['total_processed']}")
    logger.info(f"Total Predictions Made:  {stats['total_predictions']}")
    logger.info(f"Total Skipped:           {stats['total_skipped']} ({stats['total_skipped']/stats['total_processed']*100:.1f}%)")
    logger.info("--------------------------------------------------")
    logger.info(f"{'League':<25} | {'Proc':<5} | {'Pred':<5} | {'Skip':<5}")
    for league, lstats in stats["league_breakdown"].items():
        logger.info(f"{league[:25]:<25} | {lstats['processed']:<5} | {lstats['predicted']:<5} | {lstats['skipped']:<5}")
    logger.info("==================================================")

    if not predictions:
        logger.warning("No predictions met sufficiency criteria. Measurement aborted.")
        return
        
    y_true = np.array(actuals)
    y_prob = np.array(predictions)
    y_base = np.array(baselines)
    
    # Compute Comparative Metrics
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
    logger.info(f"      CALIBRATION RESULTS (N={len(predictions)})")
    logger.info("==================================================")
    logger.info(f"Model Brier Avg:    {brier_model_avg:.4f}")
    logger.info(f"Baseline Brier Avg: {brier_base_avg:.4f}")
    logger.info(f"Value Add:          {value_add:+.4f}")
    logger.info(f"Model Log Loss:     {ll_model:.4f}")
    logger.info("==================================================")
    
    print_reliability_diagram(y_true[:, 0], y_prob[:, 0], label="Home Win")
    print_reliability_diagram(y_true[:, 1], y_prob[:, 1], label="Draw")

if __name__ == "__main__":
    asyncio.run(run_backtest())

