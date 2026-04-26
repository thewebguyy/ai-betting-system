"""
experiments/staking_analysis.py
Risk engineering audit: Comparing Staking methods on Favorites (Prob > 0.5).
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

async def run_staking_test(name: str, method: str, kelly_frac: float, timeline: pd.DataFrame):
    logger.info(f"💰 Testing Staking: {name}...")
    
    config = ExperimentConfig(
        name=name,
        ev_threshold=0.01,
        min_warmup_matches=0,
        kelly_fraction=kelly_frac,
        staking_method=method,
        min_prob=0.501, # Favorites only
        max_prob=1.0
    )
    
    runner = BacktestModelRunner()
    simulator = BettingSimulator(config)
    
    current_date = None
    for i, (_, row) in enumerate(timeline.iterrows()):
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
    
    if current_date:
        simulator.finalize_day(current_date)

    history = simulator.get_history_df()
    metrics = calculate_metrics(history, 1000.0)
    
    return {
        'Strategy': name,
        'ROI (%)': metrics.get('ROI (%)', 0),
        'Profit': metrics.get('Total Profit', 0),
        'Drawdown (%)': metrics.get('Max Drawdown (%)', 0),
        'Win Rate (%)': metrics.get('Win Rate (%)', 0),
        'Final Bankroll': metrics.get('Final Bankroll', 0)
    }

async def main():
    data_dir = "backtest/data"
    loader = DataLoader(data_dir)
    # Use 150 matches for a robust test
    timeline = loader.merge_seasons('E0', ['2223', '2324']).tail(150)
    
    results = []
    
    # 1. Full Kelly (1.0)
    results.append(await run_staking_test("Full Kelly", "kelly", 1.0, timeline))
    
    # 2. 0.5 Kelly
    results.append(await run_staking_test("Half Kelly", "kelly", 0.5, timeline))
    
    # 3. 0.25 Kelly
    results.append(await run_staking_test("Quarter Kelly", "kelly", 0.25, timeline))
    
    # 4. Flat Staking (2% fixed)
    results.append(await run_staking_test("Flat (2%)", "flat", 0.0, timeline))
    
    df_results = pd.DataFrame(results)
    
    print("\n" + "="*80)
    print("                STAKING STRATEGY COMPARISON (FAVORITES ONLY)")
    print("="*80)
    print(df_results.to_string(index=False))
    print("="*80)
    
    # Conclusion logic
    best_roi = df_results.iloc[df_results['ROI (%)'].idxmax()]
    print(f"\n🏆 BEST PERFORMER: {best_roi['Strategy']} (ROI: {best_roi['ROI (%)']}%)")
    
    print("\n🧐 RISK AUDIT CONCLUSIONS:")
    if best_roi['ROI (%)'] < 0:
        print("🔴 VERDICT: NO EDGE. Even with optimized staking, the model cannot generate profit on this sample.")
    else:
        print("🟢 VERDICT: EDGE EXISTS. Profitability is possible with disciplined staking.")

if __name__ == "__main__":
    asyncio.run(main())
