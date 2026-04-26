"""
backtest/model_runner.py
Progressive model evaluator. Updates team strengths match-by-match to avoid data leakage.
"""

from typing import Dict, List, Tuple
import pandas as pd
from loguru import logger
from models.prob_model import ensemble_predict, update_elo, HOME_ADVANTAGE

class TeamState:
    def __init__(self, name: str):
        self.name = name
        self.elo = 1500.0
        self.matches_played = 0
        # Attack/Defence strengths (normalized around 1.0)
        self.attack_strength = 1.0
        self.defence_strength = 1.0
        # Recent goals history for moving averages
        self.goals_for_history = []
        self.goals_against_history = []

class BacktestModelRunner:
    def __init__(self, window_size: int = 10):
        self.teams: Dict[str, TeamState] = {}
        self.window_size = window_size
        self.league_avg_gf = 1.35  # Dynamic baseline
        self.league_avg_ga = 1.35

    def get_team(self, name: str) -> TeamState:
        if name not in self.teams:
            self.teams[name] = TeamState(name)
        return self.teams[name]

    def predict_match(self, home_name: str, away_name: str, use_calibration: bool = False) -> dict:
        """Predict match using current state BEFORE match is played."""
        h = self.get_team(home_name)
        a = self.get_team(away_name)
        
        # We use a simplified form string for backtesting
        # In real-time it's 'W,D,L...', here we'll just use a dummy or derive from history
        
        res = ensemble_predict(
            home_elo=h.elo,
            away_elo=a.elo,
            home_attack=h.attack_strength,
            home_defence=h.defence_strength,
            away_attack=a.attack_strength,
            away_defence=a.defence_strength,
            home_match_count=h.matches_played,
            away_match_count=a.matches_played,
            home_form=None,
            away_form=None,
            n_simulations=50,
            use_calibration=use_calibration
        )
        res['home_match_count'] = h.matches_played
        res['away_match_count'] = a.matches_played
        return res

    def update_state(self, home_name: str, away_name: str, h_goals: int, a_goals: int):
        """Update team states after match result."""
        h = self.get_team(home_name)
        a = self.get_team(away_name)
        
        # 1. Update ELO
        score_h = 1.0 if h_goals > a_goals else (0.5 if h_goals == a_goals else 0.0)
        new_h_elo, new_a_elo = update_elo(h.elo, a.elo, score_h)
        h.elo = new_h_elo
        a.elo = new_a_elo
        
        # 2. Update Strength histories
        h.goals_for_history.append(h_goals)
        h.goals_against_history.append(a_goals)
        a.goals_for_history.append(a_goals)
        a.goals_against_history.append(h_goals)
        
        h.matches_played += 1
        a.matches_played += 1
        
        # 3. Recalculate Strengths (Rolling window)
        # Strength = (Team Avg / League Avg)
        # Note: In a real backtest, league avg should also be a rolling window, 
        # but 1.35 is a stable long-term baseline for top leagues.
        if len(h.goals_for_history) >= 2:
            h_recent_gf = sum(h.goals_for_history[-self.window_size:]) / len(h.goals_for_history[-self.window_size:])
            h_recent_ga = sum(h.goals_against_history[-self.window_size:]) / len(h.goals_against_history[-self.window_size:])
            h.attack_strength = h_recent_gf / self.league_avg_gf
            h.defence_strength = h_recent_ga / self.league_avg_ga

        if len(a.goals_for_history) >= 2:
            a_recent_gf = sum(a.goals_for_history[-self.window_size:]) / len(a.goals_for_history[-self.window_size:])
            a_recent_ga = sum(a.goals_against_history[-self.window_size:]) / len(a.goals_against_history[-self.window_size:])
            a.attack_strength = a_recent_gf / self.league_avg_gf
            a.defence_strength = a_recent_ga / self.league_avg_ga
