"""
automation/state_manager.py
Local-first persistence layer using SQLite for zero-dependency execution.
"""

import sqlite3
import json
import os
from datetime import datetime
from loguru import logger

class StateManager:
    def __init__(self, db_path: str = "data/system.db"):
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # 1. Accounts & Health
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS accounts (
                    id INTEGER PRIMARY KEY,
                    name TEXT UNIQUE,
                    health REAL DEFAULT 100.0,
                    risk_score REAL DEFAULT 0.0,
                    max_stake REAL DEFAULT 1000.0,
                    last_updated TIMESTAMP
                )
            """)
            
            # 2. Signals
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS signals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    match_id TEXT,
                    alpha REAL,
                    timestamp TIMESTAMP,
                    status TEXT
                )
            """)
            
            # 3. Bets & Execution
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS bets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    signal_id INTEGER,
                    actual_stake REAL,
                    profit REAL,
                    clv REAL,
                    status TEXT,
                    timestamp TIMESTAMP,
                    FOREIGN KEY(signal_id) REFERENCES signals(id)
                )
            """)
            
            conn.commit()

    def log_signal(self, match_id: str, alpha: float):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO signals (match_id, alpha, timestamp, status) VALUES (?, ?, ?, ?)",
                (match_id, alpha, datetime.now(), "DETECTED")
            )
            return cursor.lastrowid

    def log_bet(self, signal_id: int, stake: float, status: str = "EXECUTED"):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO bets (signal_id, actual_stake, status, timestamp) VALUES (?, ?, ?, ?)",
                (signal_id, stake, status, datetime.now())
            )
            return cursor.lastrowid

    def update_account_health(self, name: str, health: float, risk: float):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT OR REPLACE INTO accounts (name, health, risk_score, last_updated) VALUES (?, ?, ?, ?)",
                (name, health, risk, datetime.now())
            )

    def get_account_state(self, name: str):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT health, risk_score, max_stake FROM accounts WHERE name = ?", (name,))
            return cursor.fetchone()

    def get_all_accounts(self):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT name, health, risk_score FROM accounts")
            return cursor.fetchall()
