import time
import sqlite3
import os
from loguru import logger
from automation.state_manager import StateManager

# Configuration
MODE = os.environ.get("MODE", "DEVELOPMENT")
db = StateManager()

def execution_loop():
    logger.info(f"💸 Execution Engine ONLINE (Mode: {MODE})")
    
    while True:
        try:
            # 0. CHECK TRUTH KILL SWITCH
            if os.path.exists("data/kill_switch.flag"):
                with open("data/kill_switch.flag", "r") as f:
                    if f.read().strip() == "OFF":
                        logger.critical("🚫 EXECUTION INHIBITED: Truth Layer detected NO EDGE. Staying in Paper Mode.")
                        time.sleep(10)
                        continue

            # 1. READ: Check for pending signals in SQLite
            with sqlite3.connect(db.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT id, match_id, alpha FROM signals WHERE status = 'DETECTED' LIMIT 1")
                row = cursor.fetchone()
                
                if row:
                    sig_id, match_id, alpha = row
                    
                    # 2. EXECUTE: (Mock logic for local demo)
                    logger.success(f"🔨 EXECUTING SIGNAL {sig_id}: {match_id} (Alpha: {alpha:.2%})")
                    
                    # 3. UPDATE: Persist result
                    db.log_bet(sig_id, 500.0, "SUCCESS")
                    cursor.execute("UPDATE signals SET status = 'EXECUTED' WHERE id = ?", (sig_id,))
                    conn.commit()
        except Exception as e:
            logger.error(f"❌ Execution Error: {e}")
                
        time.sleep(2) # High-frequency polling

if __name__ == "__main__":
    execution_loop()
