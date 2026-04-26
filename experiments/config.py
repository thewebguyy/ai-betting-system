"""
experiments/config.py
Configuration for backtesting experiments.
"""

from dataclasses import dataclass
from typing import Optional

@dataclass
class ExperimentConfig:
    name: str
    ev_threshold: float = 0.05
    min_warmup_matches: int = 15
    max_bets_per_day: Optional[int] = None
    kelly_fraction: float = 0.25
    initial_bankroll: float = 1000.0

# Standard Experiment Presets
EXPERIMENTS = [
    ExperimentConfig(
        name="Strict_Alpha",
        ev_threshold=0.08,
        min_warmup_matches=10,
        kelly_fraction=0.10
    ),
    ExperimentConfig(
        name="Standard_Value",
        ev_threshold=0.04,
        min_warmup_matches=5,
        kelly_fraction=0.25
    ),
    ExperimentConfig(
        name="Loose_Aggressive",
        ev_threshold=0.01,
        min_warmup_matches=0,
        kelly_fraction=0.50
    )
]
