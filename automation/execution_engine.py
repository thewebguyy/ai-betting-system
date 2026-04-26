"""
automation/execution_engine.py
Latency-aware execution engine for time-sensitive betting alpha.
"""

import time
import math
from loguru import logger

class ExecutionRouter:
    """
    Decides how much to stake and which route to take 
    based on the decay of alpha over time.
    """
    def __init__(self, decay_rate_min: float = 0.024):
        self.k = decay_rate_min
        self.fast_threshold = 30 # seconds
        self.medium_threshold = 120 # seconds

    def calculate_stake_multiplier(self, t_detected: float) -> float:
        """
        Calculates a stake multiplier based on time elapsed since detection.
        """
        elapsed_sec = time.time() - t_detected
        
        if elapsed_sec <= self.fast_threshold:
            logger.info(f"⚡ [FAST ROUTE] Latency: {elapsed_sec:.1f}s | Multiplier: 1.0x")
            return 1.0
        
        if elapsed_sec <= self.medium_threshold:
            # Linear decay of stake to reduce exposure as edge thins
            multiplier = 0.5
            logger.warning(f"⏳ [MEDIUM ROUTE] Latency: {elapsed_sec:.1f}s | Multiplier: {multiplier}x")
            return multiplier
            
        logger.error(f"❌ [ABORT] Latency: {elapsed_sec:.1f}s exceeds threshold. Edge expired.")
        return 0.0

    def estimate_realized_clv(self, initial_alpha: float, t_detected: float) -> float:
        """
        Estimates the CLV remaining at the current moment using exponential decay.
        Formula: A = A0 * e^(-k*t)
        """
        elapsed_min = (time.time() - t_detected) / 60.0
        realized_alpha = initial_alpha * math.exp(-self.k * elapsed_min)
        return realized_alpha

def execute_signal(signal: dict):
    router = ExecutionRouter()
    
    t_start = signal['timestamp'] # Time signal was FIRST detected
    
    # 1. Check Routing & Staking
    stake_mult = router.calculate_stake_multiplier(t_start)
    
    if stake_mult == 0:
        return {"status": "ABORTED", "reason": "LATE_SIGNAL"}
        
    # 2. Check Realized CLV
    current_clv = router.estimate_realized_clv(signal['alpha_0'], t_start)
    
    logger.success(f"💸 Executing bet with Expected CLV: {current_clv:.2%}")
    
    return {
        "status": "EXECUTED",
        "route": "FAST" if (time.time() - t_start) <= 30 else "MEDIUM",
        "final_stake_mult": stake_mult,
        "expected_clv": current_clv
    }

# Demo
if __name__ == "__main__":
    mock_signal = {
        'id': 'sig_99',
        'alpha_0': 0.05, # 5% initial edge
        'timestamp': time.time() - 45 # Detected 45 seconds ago
    }
    
    result = execute_signal(mock_signal)
    print(f"\nFinal Execution Result: {result}")
