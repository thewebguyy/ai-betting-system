"""
automation/adaptive_identity_engine.py
Dynamic, persona-based behavioral engine to mimic human bettors and evade detection.
"""

import random
import numpy as np
from loguru import logger
from dataclasses import dataclass
from typing import Dict, List, Optional

@dataclass
class Persona:
    name: str
    noise_bias: float # 0 to 1
    timing_mean: float # Seconds delay
    timing_std: float
    stake_volatility: float
    preferred_leagues: List[str]

from automation.aggression_controller import AggressionController

class AdaptiveIdentityEngine:
    def __init__(self, n_accounts: int = 5):
        self.personas = self._init_personas()
        self.agg_controller = AggressionController()
        self.account_states = {i: {
            'persona': random.choice(self.personas),
            'risk_score': 0.0,
            'history': [],
            'consecutive_wins': 0,
            'aggression': 0.5,
            'health': 100.0
        } for i in range(n_accounts)}

    def _init_personas(self) -> List[Persona]:
        return [
            Persona("Weekend_Warrior", 0.4, 600, 200, 0.5, ["EPL", "UCL"]),
            Persona("Chaser_Gambler", 0.6, 30, 10, 0.8, ["ALL"]),
            Persona("Casual_Fan", 0.2, 1200, 600, 0.2, ["EPL"]),
            Persona("Late_Night_Punter", 0.5, 45, 15, 0.4, ["MLS", "BRAZIL"])
        ]

    def update_state(self, account_id: int, result: dict, health: float):
        """Updates internal risk and aggression state."""
        state = self.account_states[account_id]
        state['health'] = health
        
        # Update risk (previously update_risk)
        risk_delta = 0
        if result['alpha'] > 0.04: risk_delta += 0.1
        if result['profit'] > 0: 
            state['consecutive_wins'] += 1
            if state['consecutive_wins'] > 3: risk_delta += 0.15
        else:
            state['consecutive_wins'] = 0
            risk_delta -= 0.05
            
        state['risk_score'] = max(0, min(1, state['risk_score'] + risk_delta))
        
        # Calculate new aggression level
        state['aggression'] = self.agg_controller.calculate_aggression(health, state['risk_score'])

    def get_execution_config(self, account_id: int, alpha: float, target_stake: float) -> Optional[dict]:
        """Generates a persona-aligned execution plan with aggression-tuned parameters."""
        state = self.account_states[account_id]
        persona = state['persona']
        agg = state['aggression']
        
        rules = self.agg_controller.get_allocation_rules(agg)
        
        # 1. Entropy Injection
        break_prob = 0.05 + (state['risk_score'] * 0.3)
        if random.random() < break_prob:
            return None

        # 2. Dynamic CLV Shaping (Aggression-tuned)
        if alpha > rules['clv_cap'] and random.random() < (1 - agg):
            return None

        # 3. Persona + Aggression Jitter
        delay = np.random.normal(persona.timing_mean, persona.timing_std)
        # Higher aggression = faster execution (less delay)
        delay = max(5, delay * (1 - agg * 0.5))
        
        stake_jitter = rules['stake_multiplier'] + np.random.normal(0, persona.stake_volatility)
        final_stake = target_stake * max(0.5, min(3.0, stake_jitter))

        return {
            'delay': delay,
            'stake': final_stake,
            'noise_chance': rules['noise_ratio']
        }

    def generate_noise_bet(self, account_id: int) -> Optional[dict]:
        """Generates a noise bet based on current aggression rules."""
        state = self.account_states[account_id]
        agg = state['aggression']
        rules = self.agg_controller.get_allocation_rules(agg)
        
        if random.random() > rules['noise_ratio']:
            return None
            
        return {
            'alpha': random.uniform(-0.05, -0.01),
            'stake': random.uniform(10, 50 * (1 - agg)), # Less noise stake if aggressive
            'delay': random.uniform(60, 1800),
            'is_noise': True
        }
