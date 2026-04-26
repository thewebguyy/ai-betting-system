"""
automation/jump_aware_engine.py
Execution engine that accounts for discontinuous market jumps and liquidity shocks.
"""

import time
import math
from loguru import logger

class JumpAwareEngine:
    """
    Optimizes execution timing by modeling the probability of a sudden 
    market price 'jump' that erases the informational alpha.
    """
    def __init__(self, base_lambda: float = 0.015):
        # lambda: average jumps per second for the market
        # 0.015 means a 50% chance of a jump within ~46 seconds.
        self.base_lambda = base_lambda

    def calculate_jump_probability(self, elapsed_sec: float, source_tier: int = 1) -> float:
        """
        Calculates P(Jump) using an exponential distribution: 1 - e^(-lambda * t)
        source_tier 1 = High authority (fast jump)
        source_tier 3 = Low authority (slow jump)
        """
        # Adjust lambda based on authority
        adj_lambda = self.base_lambda * (2.0 if source_tier == 1 else 1.0)
        
        p_jump = 1 - math.exp(-adj_lambda * elapsed_sec)
        return p_jump

    def get_execution_verdict(self, t_detected: float, initial_alpha: float, 
                              target_stake: float, visible_depth: float, source_tier: int = 1):
        """
        Calculates Realized Profit accounting for Jump Risk, LSF, and Effective Depth.
        """
        elapsed_sec = time.time() - t_detected
        p_jump = self.calculate_jump_probability(elapsed_sec, source_tier)
        
        # 1. Liquidity Survival Factor (LSF)
        # Higher P_jump and Higher Authority = Lower LSF (Ghost Liquidity)
        lsf = (1.0 - p_jump) * (0.8 if source_tier == 1 else 0.95)
        lsf = max(0.05, lsf) # At least 5% usually survives
        
        # 2. Effective Depth
        effective_depth = visible_depth * lsf
        
        # 3. Fill Quality (FQ) based on Effective Depth
        stake_ratio = target_stake / effective_depth if effective_depth > 0 else 100.0
        fq = (1.0 - (min(1.0, stake_ratio) * 0.5)) * (1.0 - p_jump)
        fq = max(0.0, min(1.0, fq))
        
        # 4. Realized Profit (RP)
        realized_profit = initial_alpha * (1 - p_jump) * fq
        
        logger.info(f"📊 Visible: {visible_depth} | Effective: {effective_depth:.0f} | LSF: {lsf:.1%}")
        logger.info(f"💧 FQ: {fq:.1%} | Realized Profit: {realized_profit:.2%}")

        # Execution Filter based on Effective Depth
        if effective_depth < target_stake:
            logger.error("🛑 ABORT: Target stake exceeds effective surviving liquidity.")
            return {"action": "ABORT", "reason": "LIQUIDITY_COLLAPSE"}

        if realized_profit < 0.005: 
            logger.error("🛑 ABORT: Realized profit below threshold.")
            return {"action": "ABORT", "rp": realized_profit}
        
        return {
            "action": "EXECUTE", 
            "realized_profit": realized_profit, 
            "effective_depth": effective_depth,
            "final_stake": target_stake # Stake survives because it's within effective depth
        }

# Demo
if __name__ == "__main__":
    engine = JumpAwareEngine()
    
    # Example: A Tier 1 Lineup Leak detected 40 seconds ago
    t_start = time.time() - 40 
    initial_edge = 0.06 # 6% alpha
    
    verdict = engine.get_execution_verdict(t_start, initial_edge, source_tier=1)
    print(f"\nDiscontinuous Market Verdict: {verdict}")
