"""
experiments/walk_forward.py
Walk-forward validation to check edge persistence across different time regimes.
"""

import sys
import os
import pandas as pd
import numpy as np
from loguru import logger
import asyncio

# Add project root
sys.path.append(os.getcwd())

from backtest.data_loader import DataLoader
from backtest.model_runner import BacktestModelRunner
from backtest.simulator import BettingSimulator
from backtest.metrics import calculate_metrics
from experiments.config import ExperimentConfig

async def run_window(df_window: pd.DataFrame, window_name: str, initial_bankroll: float):
    logger.info(f"📅 Processing Window: {window_name}...")
    
    config = ExperimentConfig(
        name=window_name,
        ev_threshold=0.01,
        min_warmup_matches=0, # Assuming we are mid-season
        kelly_fraction=0.0,
        staking_method="flat",
        flat_stake_pct=0.02, # 2% Flat
        min_prob=0.5, # Favorites only as per previous insight
        initial_bankroll=initial_bankroll
    )
    
    # We use a FRESH runner for each window? 
    # NO: In a walk-forward, the model state (ELO) should PERSIST. 
    # But we want to see metrics for THIS window specifically.
    
    # We'll pass the runner state forward. 
    # For this experiment, let's keep one runner and just slice the history.
    pass

async def main():
    data_dir = "backtest/data"
    loader = DataLoader(data_dir)
    # Full dataset (760 matches)
    full_timeline = loader.merge_seasons('E0', ['2223', '2324'])
    
    if full_timeline.empty:
        return

    # Configuration for the experiment
    config = ExperimentConfig(
        name="WalkForward_Base",
        ev_threshold=0.01,
        min_warmup_matches=10,
        staking_method="flat",
        flat_stake_pct=0.02,
        min_prob=0.5
    )
    
    runner = BacktestModelRunner()
    simulator = BettingSimulator(config)
    
    # We define windows of 150 matches each
    window_size = 150
    total_matches = len(full_timeline)
    
    window_results = []
    
    current_date = None
    last_bet_count = 0
    
    for i, (_, row) in enumerate(full_timeline.iterrows()):
        match_dict = row.to_dict()
        match_date = str(match_dict['date'])
        
        if current_date and match_date != current_date:
            simulator.finalize_day(current_date)
        current_date = match_date
        
        preds = runner.predict_match(match_dict['home_team'], match_dict['away_team'])
        simulator.process_match(match_dict, preds)
        
        runner.update_state(
            match_dict['home_team'], match_dict['away_team'], 
            match_dict['home_goals'], match_dict['away_goals']
        )
        
        # At each window boundary, calculate metrics for THAT window
        if (i + 1) % window_size == 0 or (i + 1) == total_matches:
            history = simulator.get_history_df()
            if history.empty: continue
            
            # Slice history to get only bets in this window
            current_history = history.iloc[last_bet_count:]
            last_bet_count = len(history)
            
            if not current_history.empty:
                # Calculate metrics for the window
                # Note: initial_bankroll for window metrics calculation 
                # should be the bankroll at the start of the window.
                start_br = current_history['bankroll'].iloc[0] - current_history['profit'].iloc[0]
                metrics = calculate_metrics(current_history, start_br)
                
                window_name = f"Matches {i+1-window_size}-{i+1}" if (i+1) % window_size == 0 else f"Last {len(current_history)} bets"
                
                window_results.append({
                    'Window': window_name,
                    'Bets': metrics.get('Total Bets', 0),
                    'ROI (%)': metrics.get('ROI (%)', 0),
                    'CLV (%)': metrics.get('Avg CLV (%)', 0),
                    'Win Rate (%)': metrics.get('Win Rate (%)', 0),
                    'Profit': round(current_history['profit'].sum(), 2)
                })
                logger.info(f"✅ Window {len(window_results)} completed: ROI {metrics.get('ROI (%)')}%")

    if current_date:
        simulator.finalize_day(current_date)

    # Comparison Table
    df_results = pd.DataFrame(window_results)
    
    print("\n" + "="*80)
    print("                WALK-FORWARD PERFORMANCE VALIDATION")
    print("="*80)
    print(df_results.to_string(index=False))
    print("="*80)
    
    # Stability Check
    avg_roi = df_results['ROI (%)'].mean()
    roi_std = df_results['ROI (%)'].std()
    avg_clv = df_results['CLV (%)'].mean()
    
    print("\n🧐 STABILITY ANALYSIS:")
    print(f"Average ROI across windows : {avg_roi:.2f}%")
    print(f"ROI Standard Deviation     : {roi_std:.2f}%")
    print(f"Average CLV across windows : {avg_clv:.2f}%")
    
    print("\n🏆 FINAL VERDICT:")
    if avg_clv > 0.5 and avg_roi > 0:
        print("✅ PERSISTENT EDGE: The model shows consistent positive CLV and ROI across regimes.")
    elif avg_clv > 0:
        print("🟡 REGIME DEPENDENT: Positive CLV exists, but ROI is highly variable.")
    else:
        print("❌ NO EDGE: Long-term market efficiency beats the model.")

if __name__ == "__main__":
    asyncio.run(main())
