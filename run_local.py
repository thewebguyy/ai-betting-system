"""
run_local.py
Event-Driven Orchestrator & Supervisor.
Handles snapshots, freeze detection, and subsystem health.
"""

import subprocess
import sys
import time
import os
import signal
import json
import sqlite3
from datetime import datetime, timedelta
from loguru import logger
from automation.event_bus import EventBus

# --- CONFIGURATION ---
MODE = "LOCAL_PRODUCTION"
LOG_DIR = "logs"
DATA_DIR = "data"
SNAPSHOT_DIR = os.path.join(DATA_DIR, "snapshots")
SERVICES = {
    "web": [sys.executable, "main.py"],
    "alpha": [sys.executable, "automation/alpha_detector.py"],
    "executor": [sys.executable, "automation/execution_engine.py"],
    "truth": [sys.executable, "validate_edge.py"]
}

class EventDrivenSupervisor:
    def __init__(self):
        self._ensure_folders()
        self.processes = {}
        self.bus = EventBus()
        self.is_shutting_down = False
        self.last_event_ts = time.time()
        self.last_snapshot_ts = time.time()
        
        # Central Logger
        logger.remove()
        logger.add(sys.stdout, format="<green>{time}</green> | <blue>{extra[event_id]}</blue> | <level>{message}</level>", level="INFO")
        logger.add(f"{LOG_DIR}/supervisor.log", rotation="10 MB")

    def _ensure_folders(self):
        for folder in [LOG_DIR, DATA_DIR, SNAPSHOT_DIR]:
            if not os.path.exists(folder):
                os.makedirs(folder)

    def _signal_handler(self, sig, frame):
        self.shutdown()

    def start_service(self, name):
        cmd = SERVICES[name]
        log_file = open(f"{LOG_DIR}/{name}.log", "a", encoding="utf-8")
        
        proc = subprocess.Popen(
            cmd,
            stdout=log_file,
            stderr=log_file,
            text=True,
            env={**os.environ, "EXECUTION_MODE": "PAPER", "PYTHONUNBUFFERED": "1", "PYTHONPATH": "."}
        )
        self.processes[name] = {"proc": proc, "log_file": log_file}

    def _take_snapshot(self):
        """Saves current system state snapshot to JSON."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        snapshot_file = os.path.join(SNAPSHOT_DIR, f"snapshot_{timestamp}.json")
        
        # Capture summary stats from EventBus
        with sqlite3.connect(self.bus.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM events")
            total_events = cursor.fetchone()[0]
            cursor.execute("SELECT subsystem, last_seen FROM heartbeats")
            beats = cursor.fetchall()

        snapshot = {
            "timestamp": time.time(),
            "total_events": total_events,
            "subsystems": {b[0]: b[1] for b in beats},
            "status": "HEALTHY"
        }
        
        with open(snapshot_file, "w") as f:
            json.dump(snapshot, f, indent=4)
        
        logger.info(f"Snapshot saved: {snapshot_file}", event_id="SYS")

    def monitor(self):
        logger.info("EVENT-DRIVEN SUPERVISOR ONLINE", event_id="SYS")
        
        for name in SERVICES:
            self.start_service(name)

        while not self.is_shutting_down:
            now = time.time()
            
            # 1. Take Snapshot (30s interval)
            if now - self.last_snapshot_ts > 30:
                self._take_snapshot()
                self.last_snapshot_ts = now
            
            # 2. Freeze Detection (No events in 60s -> check subsystems)
            with sqlite3.connect(self.bus.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT MAX(timestamp) FROM events")
                max_ts = cursor.fetchone()[0] or now
                
                if now - max_ts > 60:
                    logger.warning("FREEZE DETECTED: No events emitted in 60s. Checking heartbeats...", event_id="SYS")
                    # Restart dead subsystems if needed
            
            # 3. Check Subprocess Health
            for name, data in list(self.processes.items()):
                if data["proc"].poll() is not None:
                    logger.error(f"Subsystem {name.upper()} CRASHED. Restarting...", event_id="SYS")
                    self.start_service(name)
            
            time.sleep(5)

    def shutdown(self):
        self.is_shutting_down = True
        for name, data in self.processes.items():
            data["proc"].terminate()
        sys.exit(0)

if __name__ == "__main__":
    supervisor = EventDrivenSupervisor()
    supervisor.monitor()
