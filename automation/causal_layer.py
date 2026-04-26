"""
automation/causal_layer.py
The 'Causal Validation Layer' - Distinguishing lead-time alpha from market-lag reflections.
"""

import sqlite3
import pandas as pd
from datetime import datetime
from loguru import logger

class CausalLayer:
    def __init__(self, db_path: str = "data/causal.db"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # 1. Timeline Table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS causal_timelines (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    match_id TEXT,
                    ts_signal TIMESTAMP,
                    ts_first_market_move TIMESTAMP,
                    ts_full_adjustment TIMESTAMP,
                    entry_odds REAL,
                    closing_odds REAL,
                    category TEXT -- 'TRUE_LEAD', 'LAGGED', 'SIMULTANEOUS'
                )
            """)
            conn.commit()

    def record_timeline(self, match_id: str, ts_signal: datetime, ts_move: datetime, entry_odds: float, closing_odds: float):
        """Reconstructs the event timeline to determine causality."""
        diff = (ts_signal - ts_move).total_seconds()
        
        # Classification
        if diff < -30:
            category = "TRUE_LEAD" # Signal came 30s+ before move
        elif diff > 30:
            category = "LAGGED"    # Signal came 30s+ after move
        else:
            category = "SIMULTANEOUS"

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO causal_timelines (match_id, ts_signal, ts_first_market_move, entry_odds, closing_odds, category)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (match_id, ts_signal, ts_move, entry_odds, closing_odds, category))
        
        return category

    def calculate_cas(self) -> dict:
        """
        Computes the Causal Alpha Score (CAS).
        CAS = (True Leads / Total) * Avg_CLV_of_Leads - Lag_Penalty
        """
        with sqlite3.connect(self.db_path) as conn:
            df = pd.read_sql_query("SELECT entry_odds, closing_odds, category FROM causal_timelines", conn)
        
        if df.empty:
            return {"cas": 0.0, "status": "INSUFFICIENT_DATA"}

        df['clv'] = (df['entry_odds'] / df['closing_odds']) - 1
        
        leads = df[df['category'] == "TRUE_LEAD"]
        lags = df[df['category'] == "LAGGED"]
        
        lead_ratio = len(leads) / len(df)
        avg_lead_clv = leads['clv'].mean() if not leads.empty else 0
        
        lag_penalty = (len(lags) / len(df)) * 0.05 # 5% penalty per lag ratio
        
        cas = (lead_ratio * avg_lead_clv) - lag_penalty
        
        # Classification
        if cas > 0.02: # 2% net causal edge
            status = "STRONG CAUSAL EDGE"
        elif cas > 0.005:
            status = "WEAK EDGE"
        else:
            status = "NO CAUSAL EDGE (MARKET LAGGARD)"

        return {
            "cas": cas,
            "lead_ratio": lead_ratio,
            "lag_ratio": len(lags) / len(df),
            "avg_lead_clv": avg_lead_clv,
            "status": status,
            "total_signals": len(df)
        }
