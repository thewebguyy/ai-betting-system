"""
scripts/train_calibrator.py
Runs a backtest to collect raw probabilities and outcomes, then trains the calibrator.
"""

import sys
import os
import pandas as pd
import numpy as np
from loguru import logger

from pathlib import Path
root = Path(__file__).resolve().parent.parent
sys.path.append(str(root))

from backtest.data_loader import DataLoader
from backtest.model_runner import BacktestModelRunner
from models.calibrator import ProbabilityCalibrator
from models.calibration import ProbabilityCalibrator as MetricCalibrator # The one for reports

async def train_calibration():
    logger.info("📡 Starting calibration training process...")
    
    data_dir = "backtest/data"
    loader = DataLoader(data_dir)
    # Use a subset for faster training in demo
    timeline = loader.merge_seasons('E0', ['2223', '2324']).tail(200)
    
    if timeline.empty:
        logger.error("No historical data found. Please run backtest/run_backtest.py first to download data.")
        return

    runner = BacktestModelRunner()
    
    raw_probs = []
    outcomes = []
    
    logger.info(f"Gathering predictions for {len(timeline)} matches...")
    for i, (_, row) in enumerate(timeline.iterrows()):
        if i % 50 == 0:
            logger.info(f"Processed {i}/{len(timeline)}...")
            
        match_dict = row.to_dict()
        
        # 1. Predict (Raw)
        preds = runner.predict_match(match_dict['home_team'], match_dict['away_team'])
        
        # 2. Store probabilities (Away, Draw, Home order for calibrator)
        raw_probs.append([preds['away'], preds['draw'], preds['home']])
        
        # 3. Store outcome (0=Away, 1=Draw, 2=Home)
        res_map = {'A': 0, 'D': 1, 'H': 2}
        outcomes.append(res_map[match_dict['result']])
        
        # 4. Update runner state
        runner.update_state(
            match_dict['home_team'], 
            match_dict['away_team'], 
            match_dict['home_goals'], 
            match_dict['away_goals']
        )

    X = np.array(raw_probs)
    y = np.array(outcomes)
    
    # Split into train (fit calibration) and test (evaluate calibration)
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.3, random_state=42)
    
    # 1. Fit Logistic (Platt Scaling)
    logistic_cal = ProbabilityCalibrator(method='logistic')
    logistic_cal.fit(X_train, y_train)
    logistic_cal.save("epl_ensemble")
    
    # 2. Fit Isotonic
    isotonic_cal = ProbabilityCalibrator(method='isotonic')
    isotonic_cal.fit(X_train, y_train)
    isotonic_cal.save("epl_ensemble")
    
    # Evaluation
    logger.info("Evaluating calibration impact...")
    
    def evaluate(name, cal_obj, X_eval, y_eval):
        calibrated_probs = cal_obj.calibrate(X_eval)
        
        # We'll use our existing MetricCalibrator for the report
        # MetricCalibrator expects (prob, outcome_bool)
        # We'll check 'Home' calibration as a proxy
        metric = MetricCalibrator(n_bins=10)
        for i in range(len(y_eval)):
            prob_home = calibrated_probs[i, 2] # Home is index 2
            outcome_home = (y_eval[i] == 2)
            metric.add_data(prob_home, outcome_home)
            
        report = metric.get_report()
        ece = metric.calculate_ece()
        return ece, report

    # Before
    raw_metric = MetricCalibrator(n_bins=10)
    for i in range(len(y_test)):
        raw_metric.add_data(X_test[i, 2], (y_test[i] == 2))
    raw_ece = raw_metric.calculate_ece()
    
    log_ece, _ = evaluate("Logistic", logistic_cal, X_test, y_test)
    iso_ece, _ = evaluate("Isotonic", isotonic_cal, X_test, y_test)
    
    print("\n" + "="*50)
    print("      CALIBRATION PERFORMANCE (HOME MARKET)")
    print("="*50)
    print(f"Raw ECE      : {raw_ece:.4f}")
    print(f"Logistic ECE : {log_ece:.4f}")
    print(f"Isotonic ECE : {iso_ece:.4f}")
    print("="*50)

if __name__ == "__main__":
    import asyncio
    from sklearn.model_selection import train_test_split
    asyncio.run(train_calibration())
