"""
experiments/market_efficiency.py
Analyzing model signal timing relative to market movement (Opening vs Closing).
"""

import sys
import os
import pandas as pd
import numpy as np
from loguru import logger
import asyncio
from scipy.stats import pearsonr

# Add project root
sys.path.append(os.getcwd())

from backtest.data_loader import DataLoader
from backtest.model_runner import BacktestModelRunner
from experiments.config import ExperimentConfig

async def main():
    logger.info("🕵️ Starting Market Efficiency Analysis...")
    
    data_dir = "backtest/data"
    loader = DataLoader(data_dir)
    # Use 200 matches
    timeline = loader.merge_seasons('E0', ['2223', '2324']).tail(200)
    
    runner = BacktestModelRunner()
    
    data = []
    
    for i, (_, row) in enumerate(timeline.iterrows()):
        match_dict = row.to_dict()
        
        # 1. Predict (Raw)
        preds = runner.predict_match(match_dict['home_team'], match_dict['away_team'])
        
        # 2. Extract Odds (Market Probabilities)
        # We focus on the 'Home' market for simplicity
        p_model = preds['home']
        
        # Opening Pinnacle
        p_open = 1.0 / match_dict['opening_odds_h'] if pd.notnull(match_dict.get('opening_odds_h')) else None
        # Closing Pinnacle
        p_close = 1.0 / match_dict['closing_odds_h'] if pd.notnull(match_dict.get('closing_odds_h')) else None
        
        if p_open and p_close:
            move_direction = 1 if p_close > p_open else (-1 if p_close < p_open else 0)
            model_direction = 1 if p_model > p_open else (-1 if p_model < p_open else 0)
            
            data.append({
                'model_prob': p_model,
                'open_prob': p_open,
                'close_prob': p_close,
                'move_mag': abs(p_close - p_open),
                'aligned': (move_direction == model_direction)
            })
            
        runner.update_state(
            match_dict['home_team'], match_dict['away_team'], 
            match_dict['home_goals'], match_dict['away_goals']
        )

    df = pd.DataFrame(data)
    
    # Analysis
    corr_open, _ = pearsonr(df['model_prob'], df['open_prob'])
    corr_close, _ = pearsonr(df['model_prob'], df['close_prob'])
    
    # Aligned %: Does the model predict the DIRECTION of the market move?
    aligned_pct = df['aligned'].mean() * 100
    
    # Efficiency Score
    # If model is more correlated with CLOSE than OPEN, it's "Late" or "Absorbed"
    # If model is more correlated with OPEN, it's "Early"
    diff = corr_close - corr_open
    
    classification = "NEUTRAL"
    if diff > 0.05:
        classification = "LATE SIGNAL (Market is ahead of you)"
    elif diff < -0.05:
        classification = "EARLY SIGNAL (You are ahead of the market)"
    
    efficiency_score = (1 - abs(diff)) * 100

    print("\n" + "="*60)
    print("           MARKET EFFICIENCY & SIGNAL TIMING")
    print("="*60)
    print(f"Correlation (Model vs Opening) : {corr_open:.4f}")
    print(f"Correlation (Model vs Closing) : {corr_close:.4f}")
    print(f"Market Movement Alignment      : {aligned_pct:.2f}%")
    print("-" * 60)
    print(f"Efficiency Score               : {efficiency_score:.1f}%")
    print(f"Signal Classification          : {classification}")
    print("-" * 60)
    
    print("\n🧐 INTERPRETATION:")
    if aligned_pct > 55:
        print("✅ ALPHA DETECTED: The model correctly anticipates market movement direction.")
    else:
        print("❌ NOISE: The model is fading market moves or reacting randomly.")
        
    if classification == "LATE SIGNAL (Market is ahead of you)":
        print("⚠️ WARNING: Your model is likely just 'chasing' information already in the odds.")

if __name__ == "__main__":
    asyncio.run(main())
