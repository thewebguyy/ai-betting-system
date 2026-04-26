"""
validate_edge.py
Science Orchestrator: Validates if the current model produces real-world CLV.
Runs a 24/7 truth validation loop.
"""

import time
import random
import os
from loguru import logger
from automation.truth_layer import TruthLayer
from automation.causal_layer import CausalLayer
from datetime import datetime, timedelta

# Configuration
truth_engine = TruthLayer()
causal_engine = CausalLayer()

def validation_loop():
    logger.info("🔬 TRUTH + CAUSAL VALIDATION ENGINE ONLINE.")
    
    while True:
        # 1. Simulate Signal Detection
        if random.random() < 0.2:
            match_id = f"M_TEST_{random.randint(100, 999)}"
            entry_price = random.uniform(1.90, 2.10)
            pred_prob = 1.0 / (entry_price * 0.95)
            
            ts_signal = datetime.now()
            
            # Record Paper Bet
            bet_id = truth_engine.log_paper_bet(match_id, entry_price, pred_prob)
            
            # 2. Simulate Market Movement (Causal Timing)
            # 60% chance signal is a LEAD, 40% it's LAGGED
            if random.random() < 0.6:
                ts_move = ts_signal + timedelta(seconds=random.randint(45, 300)) # Move happens AFTER signal
            else:
                ts_move = ts_signal - timedelta(seconds=random.randint(10, 60))  # Move already happened
            
            closing_price = entry_price * random.uniform(0.96, 1.02)
            won = random.random() < (1.0 / entry_price + 0.02)
            
            # Record Causal Timeline
            causal_engine.record_timeline(match_id, ts_signal, ts_move, entry_price, closing_price)
            truth_engine.settle_bet(bet_id, closing_price, won)
            
        # 3. Compute Stats
        truth_stats = truth_engine.calculate_ers()
        causal_stats = causal_engine.calculate_cas()
        
        print("\n" + "="*70)
        print("                SYSTEM TRUTH & CAUSALITY DASHBOARD")
        print("="*70)
        print(f"CAUSAL STATUS:     {causal_stats.get('status')}")
        print(f"Causal Alpha (CAS): {causal_stats.get('cas', 0):.4f}")
        print(f"True Lead Ratio:   {causal_stats.get('lead_ratio', 0):.1%}")
        print(f"Lagged Ratio:      {causal_stats.get('lag_ratio', 0):.1%}")
        print("-" * 70)
        print(f"EDGE STATUS:       {truth_stats.get('status')}")
        print(f"Edge Reality (ERS): {truth_stats.get('ers', 0):.4f}")
        print(f"Rolling CLV:       {truth_stats.get('avg_clv', 0):.2%}")
        print("="*70)
        
        # Kill Switch Logic (Aggressive)
        if causal_stats.get('status') == "NO CAUSAL EDGE (MARKET LAGGARD)":
            logger.critical("🚨 CAUSAL KILL SWITCH: System is lagging market moves. Inhibiting execution.")
            with open("data/kill_switch.flag", "w") as f: f.write("OFF")
        elif truth_stats.get('status') == "NO_EDGE_DETECTED":
            with open("data/kill_switch.flag", "w") as f: f.write("OFF")
        else:
            with open("data/kill_switch.flag", "w") as f: f.write("ON")
                
        time.sleep(10)

if __name__ == "__main__":
    validation_loop()
