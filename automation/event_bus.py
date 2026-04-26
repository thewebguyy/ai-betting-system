"""
automation/event_bus.py
Central EventBus for decoupled, local-first communication.
Uses SQLite for cross-process event persistence and propagation.
"""

import sqlite3
import json
import uuid
import time
from datetime import datetime
from loguru import logger

class EventBus:
    def __init__(self, db_path: str = "data/events.db"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id TEXT,
                    topic TEXT,
                    payload TEXT,
                    timestamp REAL,
                    source TEXT
                )
            """)
            # For Heartbeats
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS heartbeats (
                    subsystem TEXT PRIMARY KEY,
                    last_seen REAL,
                    status TEXT
                )
            """)
            conn.commit()

    def emit(self, topic: str, payload: dict, source: str):
        event_id = payload.get("event_id", str(uuid.uuid4()))
        payload["event_id"] = event_id
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO events (event_id, topic, payload, timestamp, source) VALUES (?, ?, ?, ?, ?)",
                (event_id, topic, json.dumps(payload), time.time(), source)
            )
            conn.commit()
        
        logger.bind(event_id=event_id).info(f"📢 EVENT [{topic}] from {source}")
        return event_id

    def subscribe(self, topic: str, last_event_id: int):
        """Polls for new events on a specific topic."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, event_id, topic, payload, source FROM events WHERE topic = ? AND id > ? ORDER BY id ASC",
                (topic, last_event_id)
            )
            return cursor.fetchall()

    def heartbeat(self, subsystem: str, status: str = "ALIVE"):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT OR REPLACE INTO heartbeats (subsystem, last_seen, status) VALUES (?, ?, ?)",
                (subsystem, time.time(), status)
            )
            conn.commit()

    def get_timeline(self, event_id: str):
        """Reconstructs the full lifecycle of a signal."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT topic, payload, timestamp, source FROM events WHERE event_id = ? ORDER BY timestamp ASC",
                (event_id,)
            )
            return cursor.fetchall()
