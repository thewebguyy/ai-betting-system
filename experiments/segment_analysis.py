"""
experiments/segment_analysis.py
Runs comparative analysis across Favorites, Balanced, and Underdog segments.
"""

import sys
import os
import pandas as pd
from loguru import logger
import asyncio

# Add project root
sys.path.append(os.getcwd())

from backtest.data_loader import DataLoader
from backtest.model_runner import BacktestModelRunner
from backtest.simulator import BettingSimulator
from backtest.metrics import calculate_metrics
from experiments.config import ExperimentConfig

async def run_segment_test(name: str, min_p: float, max_p: float, timeline: pd.DataFrame):
    logger.info(f"🔍 Testing Segment: {name} ({min_p}-{max_p} prob)...")
    
    config = ExperimentConfig(
        name=name,
        ev_threshold=0.0, # Lower to get enough bets for analysis
        min_warmup_matches=0,
        kelly_fraction=0.25,
        min_prob=min_p,
        max_prob=max_p
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
        'Segment': name,
        'Bets': metrics.get('Total Bets', 0),
        'ROI (%)': metrics.get('ROI (%)', 0),
        'CLV (%)': metrics.get('Avg CLV (%)', 0),
        'Win Rate (%)': metrics.get('Win Rate (%)', 0),
        'Drawdown (%)': metrics.get('Max Drawdown (%)', 0)
    }

async def main():
    data_dir = "backtest/data"
    loader = DataLoader(data_dir)
    # Use 100 matches for faster turnaround
    timeline = loader.merge_seasons('E0', ['2223', '2324']).tail(100)
    
    results = []
    
    # 1. Favorites (> 0.5)
    res_fav = await run_segment_test("Favorites", 0.501, 1.0, timeline)
    results.append(res_fav)
    
    # 2. Balanced (0.3 - 0.5)
    res_bal = await run_segment_test("Balanced", 0.30, 0.50, timeline)
    results.append(res_bal)
    
    # 3. Underdogs (< 0.3)
    res_und = await run_segment_test("Underdogs", 0.0, 0.299, timeline)
    results.append(res_und)
    
    # Comparison Table
    df_results = pd.DataFrame(results)
    
    print("\n" + "="*80)
    print("                SEGMENTED PERFORMANCE COMPARISON")
    print("="*80)
    print(df_results.to_string(index=False))
    print("="*80)
    
    # Validation Rules
    print("\n💡 STRATEGIC INSIGHTS:")
    for _, row in df_results.iterrows():
        if row['CLV (%)'] > 0 and row['ROI (%)'] > -10:
             print(f"✅ {row['Segment']}: Potential Tradable Edge detected (CLV: {row['CLV (%)']}%)")
        elif row['CLV (%)'] < -3:
             print(f"❌ {row['Segment']}: No exploitable inefficiency. Market is too sharp or model is biased.")

if __name__ == "__main__":
    asyncio.run(main())
