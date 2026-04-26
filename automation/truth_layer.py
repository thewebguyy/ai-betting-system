"""
automation/truth_layer.py
The 'Truth Validation Layer' - A scientific engine to verify the presence of real betting edge.
Strictly Paper Trading. Zero Execution.
"""

import sqlite3
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from loguru import logger

class TruthLayer:
    def __init__(self, db_path: str = "data/truth.db"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # 1. Paper Bets
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS paper_bets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    match_id TEXT,
                    entry_odds REAL,
                    predicted_prob REAL,
                    closing_odds REAL,
                    stake REAL DEFAULT 1.0,
                    result TEXT, -- 'WIN', 'LOSS', 'PENDING'
                    timestamp TIMESTAMP
                )
            """)
            
            # 2. Daily Metrics
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS daily_metrics (
                    date TEXT PRIMARY KEY,
                    avg_clv REAL,
                    roi REAL,
                    win_rate REAL,
                    ers_score REAL,
                    signal_count INTEGER
                )
            """)
            conn.commit()

    def log_paper_bet(self, match_id: str, entry_odds: float, predicted_prob: float):
        """Records a theoretical bet at the moment of signal detection."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO paper_bets (match_id, entry_odds, predicted_prob, result, timestamp) VALUES (?, ?, ?, ?, ?)",
                (match_id, entry_odds, predicted_prob, 'PENDING', datetime.now())
            )
            return cursor.lastrowid

    def settle_bet(self, bet_id: int, closing_odds: float, won: bool):
        """Settles a paper bet and captures the closing line."""
        result = 'WIN' if won else 'LOSS'
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE paper_bets SET closing_odds = ?, result = ? WHERE id = ?",
                (closing_odds, result, bet_id)
            )

    def calculate_ers(self, rolling_days: int = 7) -> dict:
        """
        Computes the Edge Reality Score (ERS).
        ERS = Avg_CLV - Market_Efficiency_Penalty
        """
        with sqlite3.connect(self.db_path) as conn:
            df = pd.read_sql_query("SELECT entry_odds, closing_odds, result FROM paper_bets WHERE closing_odds IS NOT NULL", conn)
        
        if df.empty:
            return {"ers": 0.0, "clv": 0.0, "status": "INSUFFICIENT_DATA"}

        # CLV = (Entry Price / Closing Price) - 1
        df['clv'] = (df['entry_odds'] / df['closing_odds']) - 1
        avg_clv = df['clv'].mean()
        
        # Market Efficiency Penalty: Increases as variance of CLV decreases near 0
        # If CLV is consistently 0, the penalty wipes out any small noise-based alpha
        penalty = 0.01 / (df['clv'].std() + 0.01) if len(df) > 5 else 0.02
        
        ers = avg_clv - penalty
        
        # Kill Switch Logic
        status = "TRUE_EDGE" if ers > 0 and avg_clv > 0.01 else "NO_EDGE_DETECTED"
        
        return {
            "ers": ers,
            "avg_clv": avg_clv,
            "roi": (df[df['result'] == 'WIN']['entry_odds'].sum() - len(df)) / len(df) if len(df) > 0 else 0,
            "status": status,
            "signal_volume": len(df)
        }

    def update_daily_metrics(self):
        stats = self.calculate_ers()
        today = datetime.now().strftime('%Y-%m-%d')
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT OR REPLACE INTO daily_metrics (date, avg_clv, roi, ers_score, signal_count) VALUES (?, ?, ?, ?, ?)",
                (today, stats.get('avg_clv', 0), stats.get('roi', 0), stats.get('ers', 0), stats.get('signal_volume', 0))
            )
