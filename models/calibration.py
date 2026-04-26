"""
models/calibration.py
Tracks and evaluates the calibration of model probabilities.
Answers: "When the model says 60%, does the team actually win 60% of the time?"
"""

import pandas as pd
import numpy as np

class ProbabilityCalibrator:
    def __init__(self, n_bins: int = 10):
        self.n_bins = n_bins
        self.predictions = []
        self.actuals = []

    def add_data(self, prob: float, actual_outcome: bool):
        self.predictions.append(prob)
        self.actuals.append(1.0 if actual_outcome else 0.0)

    def get_report(self) -> pd.DataFrame:
        if not self.predictions:
            return pd.DataFrame()

        df = pd.DataFrame({
            'prob': self.predictions,
            'actual': self.actuals
        })
        
        # Create bins
        bins = np.linspace(0, 1, self.n_bins + 1)
        df['bin'] = pd.cut(df['prob'], bins=bins)
        
        report = df.groupby('bin').agg(
            n_samples=('actual', 'count'),
            mean_predicted=('prob', 'mean'),
            mean_actual=('actual', 'mean')
        ).reset_index()
        
        # Calculate Calibration Error (Expected Calibration Error approximation)
        report['abs_diff'] = (report['mean_predicted'] - report['mean_actual']).abs()
        report['weighted_diff'] = report['abs_diff'] * (report['n_samples'] / len(df))
        
        return report

    def calculate_ece(self) -> float:
        """Returns Expected Calibration Error."""
        report = self.get_report()
        if report.empty:
            return 0.0
        return report['weighted_diff'].sum()
