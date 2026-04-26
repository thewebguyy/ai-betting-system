"""
experiments/competitive_simulation.py
Simulates a competitive multi-agent market to test edge survival under latency pressure.
"""

import sys
import os
import pandas as pd
import numpy as np
from loguru import logger
import asyncio

# Add project root
sys.path.append(os.getcwd())

class CompetitiveMarket:
    def __init__(self, initial_odds: float, liquidity: float = 100000):
        self.odds = initial_odds
        self.prob = 1.0 / initial_odds
        self.liquidity = liquidity
        self.impact_factor = 0.5 # How much odds move per $1000 bet

    def place_bet(self, stake: float, agent_name: str) -> float:
        """Executes a bet and returns the odds obtained."""
        obtained_odds = self.odds
        
        # Market Impact Logic: Stake shifts probability
        # Simplified: Each $1000 shifts prob by 0.1% * impact_factor
        prob_shift = (stake / self.liquidity) * self.impact_factor
        self.prob += prob_shift
        self.odds = 1.0 / self.prob
        
        return obtained_odds

async def run_competitive_sim(matches: int = 50):
    logger.info(f"🏟️ Starting Multi-Agent Competition Sim ({matches} matches)...")
    
    agents = [
        {"name": "Sharp Agent", "delay": 0, "stake": 1000},
        {"name": "Fast Agent",  "delay": 60, "stake": 1000}, # 1m delay
        {"name": "Slow Agent",  "delay": 300, "stake": 1000} # 5m delay
    ]
    
    results = []
    
    for i in range(matches):
        # 1. Generate a True Probability and a Signal
        # Market opens at True Prob + Noise
        true_prob = 0.50
        market_open_prob = 0.45 # Under-priced (The Signal is 'Home' value)
        
        market = CompetitiveMarket(1.0 / market_open_prob)
        
        match_data = {"match": i}
        
        # 2. Agents act in order of latency
        for agent in agents:
            odds_obtained = market.place_bet(agent['stake'], agent['name'])
            # CLV relative to the FINAL market price (Closing Line)
            # We'll finalize the market later
            match_data[f"{agent['name']}_odds"] = odds_obtained

        # 3. Finalize Market (Closing Line)
        # In a real market, arbitrageurs and sharps move it to True Prob
        market.prob = true_prob
        market.odds = 1.0 / true_prob
        closing_odds = market.odds
        
        # 4. Calculate CLV per agent
        for agent in agents:
            entry = match_data[f"{agent['name']}_odds"]
            clv = (entry / closing_odds) - 1
            results.append({
                'Agent': agent['name'],
                'Latency (s)': agent['delay'],
                'Odds': entry,
                'CLV (%)': clv * 100,
                'Success': clv > 0
            })

    df = pd.DataFrame(results)
    summary = df.groupby('Agent').agg({
        'CLV (%)': 'mean',
        'Success': 'mean'
    }).reset_index()
    
    print("\n" + "="*60)
    print("           COMPETITIVE EDGE SURVIVAL AUDIT")
    print("="*60)
    print(summary.to_string(index=False))
    print("="*60)
    
    # Decay Rate
    sharp_clv = summary.loc[summary['Agent'] == 'Sharp Agent', 'CLV (%)'].values[0]
    slow_clv = summary.loc[summary['Agent'] == 'Slow Agent', 'CLV (%)'].values[0]
    decay = (sharp_clv - slow_clv) / sharp_clv * 100
    
    print(f"\n📉 EDGE DECAY: {decay:.1f}% reduction in CLV after 5 mins.")
    
    print("\n🧐 SURVIVAL VERDICT:")
    if slow_clv > 1.0:
        print("✅ ROBUST EDGE: Information is deep enough to survive competition.")
    elif sharp_clv > 2.0:
        print("🟡 LATENCY SENSITIVE: Alpha exists only for the first 60 seconds.")
    else:
        print("❌ CROWDED TRADE: No alpha remains after the first agent moves.")

if __name__ == "__main__":
    asyncio.run(run_competitive_sim())
