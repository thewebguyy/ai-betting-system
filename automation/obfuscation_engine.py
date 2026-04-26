"""
automation/obfuscation_engine.py
Engine designed to camouflage sharp betting behavior to maximize account lifespan.
"""

import random
from loguru import logger
from typing import Dict, Optional

class ObfuscationEngine:
    def __init__(self, 
                 noise_ratio: float = 0.30, 
                 max_visible_ev: float = 0.03,
                 stake_jitter: float = 0.40):
        self.noise_ratio = noise_ratio
        self.max_visible_ev = max_visible_ev
        self.stake_jitter = stake_jitter

    def filter_signal(self, alpha: float, target_stake: float) -> Optional[dict]:
        """
        Applies throttling and jitter to a high-alpha signal.
        Returns None if the bet should be skipped to preserve account health.
        """
        # 1. EV Throttling: Skip extreme alpha which is a 'Sharpness' beacon
        if alpha > 0.10: # 10%+ is too suspicious
            if random.random() < 0.7: # Skip 70% of ultra-high alpha
                logger.info("🕵️ Obfuscation: Skipping ultra-high alpha signal (>10%)")
                return None

        # 2. Stake Randomization
        jitter_factor = 1.0 + random.uniform(-self.stake_jitter, self.stake_jitter)
        final_stake = target_stake * jitter_factor

        # 3. Timing Jitter (Simulated delay in seconds)
        execution_delay = random.uniform(5.0, 45.0)

        return {
            'alpha_adj': min(alpha, self.max_visible_ev + random.uniform(0, 0.01)),
            'stake_adj': final_stake,
            'delay': execution_delay,
            'is_noise': False
        }

    def inject_noise_bet(self, available_markets: list) -> Optional[dict]:
        """
        Intentionally generates a 'Mug Bet' to blend in with retail flow.
        """
        if random.random() > self.noise_ratio:
            return None

        # Simulate a bet on a popular favorite (e.g. odds 1.3 - 1.6)
        # Usually negative EV (-2% to -5% margin)
        logger.info("🤡 Obfuscation: Injecting NOISE bet (Mug Camouflage)")
        return {
            'alpha_adj': random.uniform(-0.05, -0.02),
            'stake_adj': random.uniform(10, 50), # Small stakes for noise
            'delay': random.uniform(10, 300),
            'is_noise': True
        }

class AccountManager:
    """Manages the distribution of bets across multiple personas."""
    def __init__(self, n_accounts: int = 5):
        self.n_accounts = n_accounts
        self.account_history = {i: [] for i in range(n_accounts)}

    def route_bet(self, bet_config: dict) -> int:
        """Selects an account based on current activity patterns."""
        # Simple round-robin or least-recently-used
        return random.randint(0, self.n_accounts - 1)
