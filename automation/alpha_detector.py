import time
import random
import os
from loguru import logger
from automation.state_manager import StateManager

# Configuration
MODE = os.environ.get("MODE", "DEVELOPMENT")
db = StateManager()

def main_loop():
    logger.info(f"🚀 Alpha Detection Infrastructure ONLINE (Mode: {MODE})")
    
    while True:
        # Simulate signal detection for local demo
        if random.random() < 0.15: # 15% chance per tick
            match_id = f"M_{random.randint(1000, 9999)}"
            alpha = random.uniform(0.04, 0.09)
            
            # 1. PERSIST: Save signal to local SQLite immediately
            sig_id = db.log_signal(match_id, alpha)
            logger.info(f"📡 SIGNAL DETECTED: {match_id} | Alpha: {alpha:.2%} | ID: {sig_id}")
            
        time.sleep(5) # Tick rate

if __name__ == "__main__":
    main_loop()
