"""
models/calibrator.py
Implements Platt Scaling (Logistic) and Isotonic Regression calibration for match probabilities.
"""

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.isotonic import IsotonicRegression
from sklearn.model_selection import train_test_split
from loguru import logger
import pickle
from pathlib import Path

CALIBRATION_DIR = Path("models/cache/calibration")
CALIBRATION_DIR.mkdir(parents=True, exist_ok=True)

class ProbabilityCalibrator:
    def __init__(self, method='logistic'):
        self.method = method
        self.calibrators = {} # {market: calibrator_instance}
        self.is_fitted = False

    def fit(self, probs: np.ndarray, outcomes: np.ndarray):
        """
        probs: (N, 3) array of [home, draw, away] probabilities
        outcomes: (N,) array of 0=Away, 1=Draw, 2=Home (matches MatchPredictor convention)
        """
        # Convert outcomes to binary for each class (OVR)
        # Class order: 0=Away, 1=Draw, 2=Home
        markets = ['away', 'draw', 'home']
        
        for i, market in enumerate(markets):
            y_binary = (outcomes == i).astype(int)
            X = probs[:, i].reshape(-1, 1)
            
            # Use small subset for validation/early stopping if needed, 
            # but for Platt/Isotonic on small data we fit on the whole set or split.
            if self.method == 'logistic':
                model = LogisticRegression(penalty=None, solver='lbfgs')
                model.fit(X, y_binary)
                self.calibrators[market] = model
            elif self.method == 'isotonic':
                model = IsotonicRegression(out_of_bounds='clip')
                model.fit(X.flatten(), y_binary)
                self.calibrators[market] = model
                
        self.is_fitted = True
        logger.info(f"Calibration fitted using {self.method} method.")

    def calibrate(self, probs: np.ndarray) -> np.ndarray:
        """
        probs: (N, 3) or (3,) array
        Returns: calibrated (N, 3) or (3,) array
        """
        if not self.is_fitted:
            return probs

        input_is_1d = (probs.ndim == 1)
        if input_is_1d:
            probs = probs.reshape(1, -1)

        calibrated = np.zeros_like(probs)
        markets = ['away', 'draw', 'home']
        
        for i, market in enumerate(markets):
            X = probs[:, i].reshape(-1, 1)
            if self.method == 'logistic':
                # predict_proba returns [P(0), P(1)]
                calibrated[:, i] = self.calibrators[market].predict_proba(X)[:, 1]
            elif self.method == 'isotonic':
                calibrated[:, i] = self.calibrators[market].transform(X.flatten())

        # Normalize to sum to 1
        sums = calibrated.sum(axis=1, keepdims=True)
        # Avoid division by zero
        sums[sums == 0] = 1.0
        calibrated /= sums
        
        return calibrated[0] if input_is_1d else calibrated

    def save(self, name: str):
        path = CALIBRATION_DIR / f"{name}_{self.method}.pkl"
        with open(path, 'wb') as f:
            pickle.dump({
                'method': self.method,
                'calibrators': self.calibrators,
                'is_fitted': self.is_fitted
            }, f)
        logger.info(f"Calibration saved to {path}")

    def load(self, name: str) -> bool:
        path = CALIBRATION_DIR / f"{name}_{self.method}.pkl"
        if not path.exists():
            return False
        with open(path, 'rb') as f:
            data = pickle.load(f)
            self.method = data['method']
            self.calibrators = data['calibrators']
            self.is_fitted = data['is_fitted']
        logger.info(f"Calibration loaded from {path}")
        return True
