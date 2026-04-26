"""
automation/aggression_controller.py
Manages the balance between immediate profit (aggression) and long-term survivability.
"""

from loguru import logger

class AggressionController:
    def __init__(self, risk_limit: float = 0.85, health_threshold: float = 50.0):
        self.risk_limit = risk_limit
        self.health_threshold = health_threshold

    def calculate_aggression(self, account_health: float, current_risk: float) -> float:
        """
        Computes the optimal aggression level. 
        Pushes closer to the risk limit to capture more alpha.
        """
        risk_buffer = max(0, self.risk_limit - current_risk)
        risk_factor = risk_buffer / self.risk_limit
        
        # Health factor: If we are very healthy, we go full aggression regardless of risk
        health_factor = account_health / 100.0
        
        # Weighted Aggression
        aggression = (risk_factor * 0.6) + (health_factor * 0.4)
        
        # Linear scaling to be more aggressive early on
        return max(0.1, min(1.0, aggression))

    def classify_signal(self, alpha: float) -> str:
        if alpha > 0.07: return "TIER_A"
        if alpha > 0.04: return "TIER_B"
        return "TIER_C"

    def get_allocation_rules(self, aggression: float) -> dict:
        return {
            'clv_cap': 0.035 + (aggression * 0.065), # 3.5% to 10%
            'noise_ratio': 0.25 - (aggression * 0.2), # 25% to 5%
            'stake_multiplier': 0.8 + (aggression * 2.2) # 0.8x to 3.0x
        }
