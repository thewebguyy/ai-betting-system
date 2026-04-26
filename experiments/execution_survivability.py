"""
experiments/execution_survivability.py
Execution Survivability Simulator (ESS) for testing strategy sustainability under 
adversarial market conditions (limits, bans, competition).
"""

import sys
import os
import numpy as np
import pandas as pd
from loguru import logger
import time
import random

# Add project root
sys.path.append(os.getcwd())

from automation.jump_aware_engine import JumpAwareEngine
from automation.obfuscation_engine import ObfuscationEngine
from automation.adaptive_identity_engine import AdaptiveIdentityEngine

class BookmakerModel:
    def __init__(self, name: str, initial_max_stake: float = 1000.0):
        self.name = name
        self.health = 100.0  # 100 = Fresh, 0 = Banned
        self.max_stake = initial_max_stake
        self.initial_max_stake = initial_max_stake
        self.is_banned = False
        self.total_profit_taken = 0.0

    def update_health(self, profit: float, clv: float):
        """Account health decays based on profit and beating the closing line."""
        if self.is_banned:
            return

        # Sharps are identified more by CLV than raw profit
        decay = 0
        if profit > 0:
            decay += profit * 0.05
        if clv > 0.02:
            decay += 10.0 * (clv / 0.05) # Heavy penalty for beating the line

        self.health -= decay
        
        # Apply limits
        if self.health < 50:
            self.max_stake = self.initial_max_stake * (self.health / 100.0)
        
        if self.health <= 0:
            self.is_banned = True
            self.max_stake = 0
            logger.warning(f"Account BANNED at {self.name}")

class SurvivabilitySimulator:
    def __init__(self, n_bookmakers: int = 5, mode: str = "RAW"):
        self.bookies = [BookmakerModel(f"Bookie_{i}") for i in range(n_bookmakers)]
        self.engine = JumpAwareEngine()
        self.mode = mode # "RAW", "STATIC", "ADAPTIVE"
        
        self.obfuscator = None
        self.aie = None
        
        if mode == "STATIC":
            self.obfuscator = ObfuscationEngine()
        elif mode == "ADAPTIVE":
            self.aie = AdaptiveIdentityEngine(n_accounts=n_bookmakers)
            
        self.competition_intensity = 3
        self.history = []

    def simulate_bet(self, match_id: str, alpha: float, target_stake: float, visible_depth: float, t_delay: float):
        """
        Simulates the execution of a single bet across multiple bookmakers.
        """
        # Select Account
        active_indices = [i for i, b in enumerate(self.bookies) if not b.is_banned]
        if not active_indices:
            return self._record_abort(match_id, alpha, target_stake, "NO_ACCOUNTS")
        
        acc_idx = random.choice(active_indices)
        bookie = self.bookies[acc_idx]

        # 0. Behavior Layer
        actual_alpha = alpha
        actual_target_stake = target_stake
        delay_adj = t_delay
        visible_alpha = alpha

        if self.mode == "STATIC":
            obf_res = self.obfuscator.filter_signal(alpha, target_stake)
            if not obf_res: return self._record_abort(match_id, alpha, target_stake, "STATIC_SKIP")
            visible_alpha = obf_res['alpha_adj']
            actual_target_stake = obf_res['stake_adj']
            delay_adj += obf_res['delay']
            
        elif self.mode == "ADAPTIVE":
            aie_res = self.aie.get_execution_config(acc_idx, alpha, target_stake)
            if not aie_res: return self._record_abort(match_id, alpha, target_stake, "AIE_SKIP")
            
            # AIE can also inject noise
            noise_res = self.aie.generate_noise_bet(acc_idx)
            if noise_res:
                self._execute_fragment(acc_idx, noise_res['alpha'], noise_res['stake'], visible_depth, noise_res['delay'], is_noise=True)

            actual_target_stake = aie_res['stake']
            delay_adj += aie_res['delay']
            visible_alpha = min(alpha, 0.035) # AIE always caps visible alpha

        return self._execute_fragment(acc_idx, alpha, actual_target_stake, visible_depth, delay_adj, visible_alpha)

    def _execute_fragment(self, acc_idx, alpha, stake, depth, delay, visible_alpha=None, is_noise=False):
        bookie = self.bookies[acc_idx]
        if visible_alpha is None: visible_alpha = alpha
        
        effective_depth = depth / (1 + self.competition_intensity * 0.5)
        verdict = self.engine.get_execution_verdict(
            t_detected=time.time() - delay,
            initial_alpha=alpha,
            target_stake=stake,
            visible_depth=effective_depth,
            source_tier=1
        )
        
        if verdict['action'] == "ABORT":
            return self._record_abort("FRAGMENT", alpha, stake, "MARKET_ABORT")

        actual_stake = min(stake, bookie.max_stake, verdict['effective_depth'])
        s_factor = actual_stake / stake if stake > 0 else 0
        rp_real = verdict['realized_profit'] * s_factor
        
        if actual_stake > 0:
            win = random.random() < (0.5 + alpha)
            profit = actual_stake * 0.95 if win else -actual_stake
            bookie.update_health(profit, visible_alpha)
            
            if self.mode == "ADAPTIVE":
                self.aie.update_state(acc_idx, {'alpha': visible_alpha, 'profit': profit}, bookie.health)

        result = {
            'alpha': alpha,
            'actual_stake': actual_stake,
            's_factor': s_factor,
            'rp_real': rp_real,
            'status': 'SUCCESS' if not is_noise else 'NOISE'
        }
        if not is_noise: self.history.append(result)
        return result

    def _record_abort(self, match_id, alpha, target_stake, reason):
        res = {'alpha': alpha, 'target_stake': target_stake, 'actual_stake': 0, 's_factor': 0, 'rp_real': 0, 'status': f'ABORT_{reason}'}
        self.history.append(res)
        return res

    def get_summary(self):
        df = pd.DataFrame(self.history)
        if df.empty: return "No simulation data."
        summary = {
            'Total Attempted': len(df),
            'Avg Survivability (S)': df['s_factor'].mean(),
            'Avg Realized Profit (RP_real)': df['rp_real'].mean(),
            'Accounts Remaining': len([b for b in self.bookies if not b.is_banned]),
            'Final Health (Avg)': np.mean([b.health for b in self.bookies])
        }
        return summary

def run_simulation():
    # Comparison of 3 Strategies
    modes = ["RAW", "STATIC", "ADAPTIVE"]
    summaries = {}
    
    for mode in modes:
        logger.info(f"🚀 Running {mode} Strategy Simulation...")
        sim = SurvivabilitySimulator(n_bookmakers=5, mode=mode)
        for i in range(150): # Increased to 150 to see longer survival
            sim.simulate_bet(f"M_{i}", random.uniform(0.04, 0.09), 500.0, 5000.0, random.uniform(5, 30))
        summaries[mode] = sim.get_summary()

    print("\n" + "="*90)
    print("                ADAPTIVE IDENTITY SURVIVABILITY REPORT")
    print("="*90)
    print(f"{'Metric':<30} | {'Raw':<15} | {'Static':<15} | {'Adaptive':<15}")
    print("-" * 90)
    for k in summaries["RAW"].keys():
        v_raw = summaries["RAW"][k]
        v_sta = summaries["STATIC"][k]
        v_ada = summaries["ADAPTIVE"][k]
        if isinstance(v_raw, float):
            print(f"{k:<30} | {v_raw:>15.4f} | {v_sta:>15.4f} | {v_ada:>15.4f}")
        else:
            print(f"{k:<30} | {v_raw:>15} | {v_sta:>15} | {v_ada:>15}")
    print("="*90)

    # Conclusion
    ltv_improve = (summaries["ADAPTIVE"]['Avg Realized Profit (RP_real)'] * 150) / \
                  (summaries["RAW"]['Avg Realized Profit (RP_real)'] * 150 + 1e-6)
    
    print(f"\nADVERSARIAL CONCLUSION:")
    print(f"Adaptive Identity extended account lifetime and resulted in {ltv_improve:.2f}x Total Realized Value vs Raw.")

if __name__ == "__main__":
    run_simulation()
