import time
import json
import sqlite3
from datetime import datetime, timedelta
from automation.base_subsystem import BaseSubsystem

class AlphaDetector(BaseSubsystem):
    def __init__(self, db_path: str = "data/causal.db"):
        super().__init__("ALPHA")
        # Primary application DB where real value bets are stored
        self.main_db = "db/betting.db" 
        self.last_check_ts = datetime.utcnow() - timedelta(minutes=1)

    def run(self):
        self.log("Alpha Detector ONLINE. Monitoring REAL-WORLD signals...")
        
        while True:
            self.heartbeat()
            
            try:
                # 1. Poll for REAL value bets from the main system
                # In a real setup, we'd use SQLAlchemy, but for this lightweight broker, direct SQL is faster.
                with sqlite3.connect(self.main_db) as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        "SELECT id, match_id, bookmaker, market, selection, decimal_odds, ev, detected_at FROM value_bets WHERE detected_at > ? ORDER BY detected_at ASC",
                        (self.last_check_ts.isoformat(),)
                    )
                    rows = cursor.fetchall()

                for row in rows:
                    vid, match_id, bookie, market, selection, odds, ev, ts_str = row
                    
                    # Update local cursor
                    try:
                        self.last_check_ts = datetime.fromisoformat(ts_str)
                    except:
                        self.last_check_ts = datetime.utcnow()

                    # 2. Validation / Filtering Logic
                    if odds <= 1.0 or ev < 0.01:
                        self.log(f"REJECTED INVALID SIGNAL: {match_id} (Odds: {odds}, EV: {ev})", level="WARNING")
                        continue

                    # 3. Enriched Real-World Payload
                    payload = {
                        "match_id": str(match_id),
                        "odds_at_detection": float(odds),
                        "ts_detected": time.time(),
                        "ev_predicted": float(ev),
                        "selection": selection,
                        "market": market,
                        # Requirement 2: Source Tagging
                        "source_name": bookie,
                        "signal_type": "VALUE_BET"
                    }
                    
                    # 4. EMIT SIGNAL_DETECTED (HIGH Priority)
                    event_id = self.bus.emit("SIGNAL_DETECTED", payload, self.name, priority="HIGH")
                    self.log(f"REAL ALPHA CAPTURED: {match_id} from {bookie} @ {odds}", event_id)

            except Exception as e:
                self.log(f"Alpha Detector Error: {e}", level="ERROR")
            
            time.sleep(10) # Poll every 10s for real-world validation

if __name__ == "__main__":
    AlphaDetector().run()
