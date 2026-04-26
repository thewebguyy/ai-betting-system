"""
automation/walk_forward.py
The 'Walk-Forward Validation Engine' - Detecting overfitting and edge decay via time-based folds.
"""

import pandas as pd
import numpy as np
from loguru import logger

class WalkForwardValidator:
    def __init__(self, data: pd.DataFrame):
        self.data = data # Chronological dataset with signals and market results
        self.folds = []

    def run_validation(self, train_size: int = 100, test_size: int = 50):
        """
        Implements chronological fold separation.
        Train on N, Test on M, then shift window by M.
        """
        logger.info(f"🧪 Starting Walk-Forward Validation (Train: {train_size}, Test: {test_size})")
        
        results = []
        n = len(self.data)
        
        for start in range(0, n - train_size - test_size, test_size):
            train_fold = self.data.iloc[start : start + train_size]
            test_fold = self.data.iloc[start + train_size : start + train_size + test_size]
            
            fold_metrics = self._evaluate_fold(train_fold, test_fold)
            results.append(fold_metrics)
            
        return pd.DataFrame(results)

    def _evaluate_fold(self, train, test):
        """Compares train vs test performance to detect leakage and overfitting."""
        train_clv = train['clv'].mean()
        test_clv = test['clv'].mean()
        
        # Generalization Score components
        gap = abs(train_clv - test_clv)
        stability = 1.0 - (test['clv'].std() / (abs(test_clv) + 0.01))
        
        return {
            "train_clv": train_clv,
            "test_clv": test_clv,
            "gap": gap,
            "stability": stability,
            "test_roi": (test[test['result'] == 'WIN']['odds'].sum() - len(test)) / len(test)
        }

    def analyze_results(self, results: pd.DataFrame) -> dict:
        """Computes the final Generalization Score (GS) and Edge Status."""
        if results.empty:
            return {"status": "INSUFFICIENT_DATA"}

        avg_test_clv = results['test_clv'].mean()
        avg_gap = results['gap'].mean()
        clv_trend = np.polyfit(range(len(results)), results['test_clv'], 1)[0]
        
        # Generalization Score (GS)
        gs = avg_test_clv - (avg_gap * 0.5) + (clv_trend * 10)
        
        # Edge Classification
        if gs > 0.015 and clv_trend > -0.001:
            status = "DEPLOYABLE EDGE"
        elif gs > 0.005:
            status = "WEAK / UNSTABLE EDGE"
        else:
            status = "NO EDGE (OVERFITTED)"
            
        return {
            "gs_score": gs,
            "avg_test_clv": avg_test_clv,
            "clv_drift": clv_trend,
            "overfit_gap": avg_gap,
            "status": status,
            "n_folds": len(results)
        }
