"""
scripts/pseudo_execution.py
Hypothesis-Driven Pseudo-Execution Module for AI Betting Research.
Analyzes lag data to form hypotheses and simulates pseudo-executions over CLV observations.
"""

import json
import os
import hashlib
import numpy as np
from scipy import stats
from datetime import datetime
from loguru import logger
from backend.config import get_settings

settings = get_settings()

try:
    CLV_LOG = settings.clv_log_path
except AttributeError:
    CLV_LOG = "logs/clv_observations.jsonl"

try:
    LAG_LOG = settings.lag_log_path
except AttributeError:
    LAG_LOG = "logs/lag_analysis.jsonl"

PSEUDO_LOG = "logs/pseudo_execution.jsonl"
HYPOTHESES_LOG = "logs/hypotheses.jsonl"

def append_jsonl(filepath, row_dict):
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, "a", encoding="utf-8") as f:
        f.write(json.dumps(row_dict) + "\n")

def read_jsonl(filepath):
    if not os.path.exists(filepath):
        return []
    data = []
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                data.append(json.loads(line))
    return data

def generate_hypotheses():
    """Step 1: Analyzes lag_analysis.jsonl to find consistent lag patterns"""
    if not os.path.exists(LAG_LOG):
        logger.warning(f"Lag log not found: {LAG_LOG}")
        return []
        
    lags = read_jsonl(LAG_LOG)
    if not lags:
        return []
        
    # Group by league, market_type, local_bookmaker
    grouped = {}
    for l in lags:
        key = (l.get('league', 'Unknown'), l.get('market_type', '1X2'), l.get('local_bookmaker', 'Unknown'))
        if key not in grouped:
            grouped[key] = []
        grouped[key].append(l['lag_seconds'])
        
    # Read existing hypotheses to avoid duplication
    existing_hyps = read_jsonl(HYPOTHESES_LOG)
    existing_ids = {h['id'] for h in existing_hyps}
    
    hypotheses = {}
    for h in existing_hyps:
        hypotheses[h['id']] = h

    new_count = 0
    for (league, market, bookie), lag_vals in grouped.items():
        if len(lag_vals) >= 3:  # Sample requirement for consistency
            avg_lag = np.mean(lag_vals)
            if avg_lag > 5:  # Actionable lag baseline
                hyp_str = f"{league}_{market}_{bookie}"
                hyp_id = "HYP_" + hashlib.md5(hyp_str.encode()).hexdigest()[:8]
                
                if hyp_id not in existing_ids:
                    hyp = {
                        "id": hyp_id,
                        "description": f"Lag > {avg_lag:.1f}s for {bookie} on {market} in {league}",
                        "league": league,
                        "market_type": market,
                        "bookmaker": bookie,
                        "avg_lag_seconds": float(avg_lag),
                        "frequency": len(lag_vals),
                        "created_at": datetime.utcnow().isoformat()
                    }
                    hypotheses[hyp_id] = hyp
                    append_jsonl(HYPOTHESES_LOG, hyp)
                    existing_ids.add(hyp_id)
                    new_count += 1
                else:
                    # Update frequency and avg_lag
                    hypotheses[hyp_id]["frequency"] = len(lag_vals)
                    hypotheses[hyp_id]["avg_lag_seconds"] = float(avg_lag)
                    
    logger.info(f"Generated {new_count} new hypotheses. Total active: {len(hypotheses)}")
    return list(hypotheses.values())

def simulate_pseudo_execution(hypotheses):
    """Step 2: Simulate pseudo-executions for each hypothesis using CLV observations"""
    if not os.path.exists(CLV_LOG):
        logger.warning(f"CLV log not found: {CLV_LOG}")
        return hypotheses
        
    clv_obs = read_jsonl(CLV_LOG)
    if not clv_obs:
        return hypotheses
        
    existing_pseudo = read_jsonl(PSEUDO_LOG)
    # create a signature to prevent duplicate pseudo-bets
    # sign = hyp_id + timestamp + market
    existing_pseudo_sigs = {f"{b['hypothesis_id']}_{b['timestamp']}_{b['market']}" for b in existing_pseudo}

    for hyp in hypotheses:
        simulated_bets = [b for b in existing_pseudo if b['hypothesis_id'] == hyp['id']]
        
        for obs in clv_obs:
            obs_league = obs.get('league', 'Unknown')
            obs_market = obs.get('market_type', '1X2')
            
            # Target observations matching hypothesis league and market geometry
            if obs_league == hyp['league'] and obs_market == hyp['market_type']:
                model_prob = obs.get('model_prob', 0)
                market_odds = obs.get('market_odds', obs.get('odds', 0))
                closing_odds = obs.get('closing_odds', 0)
                
                if market_odds > 0 and model_prob > 0:
                    market_prob = 1.0 / market_odds
                    pseudo_clv = model_prob - market_prob
                    
                    timestamp = obs.get('timestamp', datetime.utcnow().isoformat())
                    sig = f"{hyp['id']}_{timestamp}_{obs_market}"
                    
                    if sig not in existing_pseudo_sigs:
                        sim_bet = {
                            "hypothesis_id": hyp['id'],
                            "timestamp": timestamp,
                            "market": obs_market,
                            "model_odds": 1.0 / model_prob if model_prob > 0 else 0,
                            "closing_odds": closing_odds,
                            "market_odds_at_lag": market_odds,
                            "pseudo_clv": pseudo_clv
                        }
                        simulated_bets.append(sim_bet)
                        append_jsonl(PSEUDO_LOG, sim_bet)
                        existing_pseudo_sigs.add(sig)
                    
        hyp['simulated_bets'] = simulated_bets
        
        # Calculate stats
        clv_vals = [b['pseudo_clv'] for b in simulated_bets]
        if len(clv_vals) > 1:
            hyp['sample_size'] = len(clv_vals)
            hyp['mean_clv'] = float(np.mean(clv_vals))
            hyp['std_clv'] = float(np.std(clv_vals))
            hyp['skew'] = float(stats.skew(clv_vals))
            
            # Hypothesis test: H0: mean_clv = 0
            # Ensure variance is not exactly zero to avoid warnings/divide by zero
            if np.var(clv_vals) > 1e-9:
                t_stat, p_val = stats.ttest_1samp(clv_vals, 0)
                hyp['p_value'] = float(p_val)
            else:
                hyp['p_value'] = 1.0
        else:
            hyp['sample_size'] = len(clv_vals)
            hyp['mean_clv'] = float(np.mean(clv_vals)) if len(clv_vals) == 1 else 0.0
            hyp['std_clv'] = 0.0
            hyp['skew'] = 0.0
            hyp['p_value'] = 1.0
            
    return hypotheses

def run_pseudo_execution_workflow():
    logger.info("Running standard pseudo-execution workflow...")
    hypotheses = generate_hypotheses()
    if hypotheses:
        hypotheses = simulate_pseudo_execution(hypotheses)
    return hypotheses

if __name__ == "__main__":
    run_pseudo_execution_workflow()

