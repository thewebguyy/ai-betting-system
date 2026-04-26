"""
experiments/runner.py
Core engine for running multiple betting strategy experiments.
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
from experiments.config import EXPERIMENTS, ExperimentConfig

async def run_single_experiment(config: ExperimentConfig, timeline: pd.DataFrame):
    logger.info(f"🧪 Running Experiment: {config.name}...")
    
    runner = BacktestModelRunner()
    simulator = BettingSimulator(config)
    
    current_date = None
    
    for i, (_, row) in enumerate(timeline.iterrows()):
        match_dict = row.to_dict()
        
        # Day transition logic for bet caps
        match_date = str(match_dict['date'])
        if current_date and match_date != current_date:
            simulator.finalize_day(current_date)
        current_date = match_date
        
        # 1. Predict
        preds = runner.predict_match(match_dict['home_team'], match_dict['away_team'])
        
        # 2. Process (Potential Bet)
        simulator.process_match(match_dict, preds)
        
        # 3. Update State
        runner.update_state(
            match_dict['home_team'], 
            match_dict['away_team'], 
            match_dict['home_goals'], 
            match_dict['away_goals']
        )
    
    # Finalize last day
    if current_date:
        simulator.finalize_day(current_date)

    history_df = simulator.get_history_df()
    metrics = calculate_metrics(history_df, config.initial_bankroll)
    calibration = simulator.calibrator.get_report()
    ece = simulator.calibrator.calculate_ece()
    
    return {
        "config": config,
        "metrics": metrics,
        "calibration": calibration,
        "ece": ece
    }

async def main():
    data_dir = "backtest/data"
    loader = DataLoader(data_dir)
    # We use a 100-match window for this demo to show variance
    timeline = loader.merge_seasons('E0', ['2223', '2324']).tail(100)
    
    results = []
    for cfg in EXPERIMENTS:
        res = await run_single_experiment(cfg, timeline)
        results.append(res)
        
    print("\n" + "="*80)
    print(f"{'EXPERIMENT':<20} | {'BETS':<6} | {'ROI %':<8} | {'PROFIT':<10} | {'ECE':<8}")
    print("-" * 80)
    for r in results:
        cfg = r['config']
        m = r['metrics']
        print(f"{cfg.name:<20} | {m.get('Total Bets', 0):<6} | {m.get('ROI (%)', 0):<8} | {m.get('Total Profit', 0):<10} | {r['ece']:.4f}")
    print("="*80)

    # Detailed calibration for the 'Standard' experiment
    standard_res = results[1]
    if not standard_res['calibration'].empty:
        print("\nPROBABILITY CALIBRATION (Standard_Value):")
        print(standard_res['calibration'][['bin', 'n_samples', 'mean_predicted', 'mean_actual']])
    else:
        print("\nPROBABILITY CALIBRATION (Standard_Value): No data collected.")

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
