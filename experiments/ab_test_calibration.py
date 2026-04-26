"""
experiments/ab_test_calibration.py
Controlled A/B test comparing Raw vs Calibrated model performance.
"""

import sys
import os
import pandas as pd
from loguru import logger

# Add project root
sys.path.append(os.getcwd())

from backtest.data_loader import DataLoader
from backtest.model_runner import BacktestModelRunner
from backtest.simulator import BettingSimulator
from backtest.metrics import calculate_metrics
from experiments.config import ExperimentConfig

async def run_backtest_instance(use_calibration: bool, timeline: pd.DataFrame, name: str):
    config = ExperimentConfig(
        name=name,
        ev_threshold=0.03,
        min_warmup_matches=5,
        kelly_fraction=0.25
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
        
        # Predict with or without calibration
        preds = runner.predict_match(
            match_dict['home_team'], 
            match_dict['away_team'], 
            use_calibration=use_calibration
        )
        
        simulator.process_match(match_dict, preds)
        
        runner.update_state(
            match_dict['home_team'], 
            match_dict['away_team'], 
            match_dict['home_goals'], 
            match_dict['away_goals']
        )
    
    if current_date:
        simulator.finalize_day(current_date)

    return simulator.get_history_df(), simulator

async def main():
    logger.info("🧪 Starting A/B Test: Raw vs Calibrated probabilities...")
    
    data_dir = "backtest/data"
    loader = DataLoader(data_dir)
    # Use 100 matches for the test
    timeline = loader.merge_seasons('E0', ['2223', '2324']).tail(100)
    
    # Run A: Raw
    history_a, sim_a = await run_backtest_instance(False, timeline, "Raw_Model")
    metrics_a = calculate_metrics(history_a, 1000.0)
    
    # Run B: Calibrated
    history_b, sim_b = await run_backtest_instance(True, timeline, "Calibrated_Model")
    metrics_b = calculate_metrics(history_b, 1000.0)
    
    # Breakdown Analysis
    def get_breakdown(df):
        if df.empty: return {}
        # Avg odds
        avg_odds = df['odds'].mean()
        # Favorites (odds < 2.0)
        fav_pct = (df['odds'] < 2.0).mean() * 100
        return {"avg_odds": avg_odds, "fav_pct": fav_pct}

    break_a = get_breakdown(history_a)
    break_b = get_breakdown(history_b)

    print("\n" + "="*60)
    print(f"{'METRIC':<20} | {'RAW MODEL':<15} | {'CALIBRATED':<15}")
    print("-" * 60)
    common_metrics = ['Total Bets', 'ROI (%)', 'Total Profit', 'Win Rate (%)', 'Max Drawdown (%)', 'Avg CLV (%)']
    for m in common_metrics:
        val_a = metrics_a.get(m, 0)
        val_b = metrics_b.get(m, 0)
        print(f"{m:<20} | {val_a:<15} | {val_b:<15}")
    
    print("-" * 60)
    print(f"{'Avg Odds':<20} | {break_a.get('avg_odds', 0):.2f}           | {break_b.get('avg_odds', 0):.2f}")
    print(f"{'Favorite Bet %':<20} | {break_a.get('fav_pct', 0):.1f}%          | {break_b.get('fav_pct', 0):.1f}%")
    print("="*60)

    # Summary
    if metrics_b.get('ROI (%)', -100) > metrics_a.get('ROI (%)', -100):
        print("\n🏆 VERDICT: Calibrated Model outperformed the Raw Model.")
    else:
        print("\n🏆 VERDICT: Raw Model outperformed the Calibrated Model.")

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
