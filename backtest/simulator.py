"""
backtest/simulator.py
The betting execution engine. Simulates stakes and bankroll growth.
"""

from typing import List, Dict, Optional
import pandas as pd
from loguru import logger
from experiments.config import ExperimentConfig
from models.calibration import ProbabilityCalibrator

class BettingSimulator:
    def __init__(self, config: ExperimentConfig):
        self.config = config
        self.bankroll = config.initial_bankroll
        self.history = []
        self.calibrator = ProbabilityCalibrator()
        # Track daily bets for the cap
        self.daily_bets = {} # date -> list of possible bets

    def process_match(self, match: dict, predictions: dict):
        """
        Evaluate if a bet should be placed.
        Instead of immediate execution, we store potential bets per day to apply caps later.
        """
        # 1. Warm-up filter
        h_count = predictions.get('home_match_count', 0) # Need to ensure these are passed
        a_count = predictions.get('away_match_count', 0)
        
        # We need to get these counts from the runner or the prediction dict
        # Updating ensemble_predict earlier didn't include these in the return dict 
        # unless they were passed in. Let's assume they are there.
        
        if (predictions.get('home_match_count', 0) < self.config.min_warmup_matches or 
            predictions.get('away_match_count', 0) < self.config.min_warmup_matches):
            return

        odds_map = {'home': match['odds_h'], 'draw': match['odds_d'], 'away': match['odds_a']}
        
        best_market = None
        max_ev = -1.0
        
        for market in ['home', 'draw', 'away']:
            prob = predictions[market]
            odds = odds_map[market]
            ev = (prob * odds) - 1
            
            # Track calibration for ALL predictions we consider
            actual_res = 'home' if match['result'] == 'H' else ('draw' if match['result'] == 'D' else 'away')
            self.calibrator.add_data(prob, (market == actual_res))

            if ev > self.config.ev_threshold and ev > max_ev:
                max_ev = ev
                best_market = market

        if best_market:
            date_key = str(match['date'])
            if date_key not in self.daily_bets:
                self.daily_bets[date_key] = []
            
            self.daily_bets[date_key].append({
                'match': match,
                'predictions': predictions,
                'market': best_market,
                'ev': max_ev
            })

    def finalize_day(self, date_key: str):
        """Execute bets for a given day after applying caps."""
        if date_key not in self.daily_bets:
            return

        potential_bets = self.daily_bets[date_key]
        # Sort by EV descending
        potential_bets.sort(key=lambda x: x['ev'], reverse=True)
        
        # Apply cap
        if self.config.max_bets_per_day:
            potential_bets = potential_bets[:self.config.max_bets_per_day]

        for bet in potential_bets:
            self._execute_bet(bet)

    def _execute_bet(self, bet: dict):
        match = bet['match']
        market = bet['market']
        prob = bet['predictions'][market]
        odds = match[f"odds_{market[0]}"] # odds_h, odds_d, odds_a
        
        actual_res = 'home' if match['result'] == 'H' else ('draw' if match['result'] == 'D' else 'away')
        
        # Kelly
        raw_kelly = (prob * odds - 1) / (odds - 1)
        stake_pct = max(0, min(0.15, raw_kelly * self.config.kelly_fraction))
        stake_amt = self.bankroll * stake_pct
        
        is_win = (market == actual_res)
        profit = stake_amt * (odds - 1) if is_win else -stake_amt
        
        self.bankroll += profit
        
        self.history.append({
            'date': match['date'],
            'home': match['home_team'],
            'away': match['away_team'],
            'market': market,
            'prob': prob,
            'odds': odds,
            'ev': bet['ev'],
            'stake_pct': stake_pct,
            'stake_amt': stake_amt,
            'is_win': is_win,
            'profit': profit,
            'bankroll': self.bankroll,
            'clv': (odds / match.get(f'closing_odds_{market[0]}', odds)) - 1
        })

    def get_history_df(self) -> pd.DataFrame:
        return pd.DataFrame(self.history)
