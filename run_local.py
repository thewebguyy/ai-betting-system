"""
run_local.py
Main orchestrator and process supervisor for local-first execution.
Manages the web dashboard, alpha detector, and execution engine.
"""

import subprocess
import sys
import time
import os
from datetime import datetime, timedelta
from loguru import logger

# Configuration
MODE = "LOCAL_PRODUCTION"
LOG_DIR = "logs"
SERVICES = {
    "web": [sys.executable, "main.py"],
    "alpha": [sys.executable, "automation/alpha_detector.py"],
    "executor": [sys.executable, "automation/execution_engine.py"],
    "truth": [sys.executable, "validate_edge.py"]
}

class LocalSupervisor:
    def __init__(self):
        os.makedirs(LOG_DIR, exist_ok=True)
        os.makedirs("data", exist_ok=True)
        self.processes = {}
        self.health_stats = {name: {"restarts": 0, "last_crash": None, "history": []} for name in SERVICES}
        
        # Configure Loguru for system monitoring
        logger.add(f"{LOG_DIR}/system.log", rotation="10 MB", level="INFO", 
                   format="{time} | {level} | {message}")

    def start_service(self, name):
        cmd = SERVICES[name]
        log_file = open(f"{LOG_DIR}/{name}.log", "a")
        
        logger.info(f"🚀 Starting service: {name} (Cmd: {' '.join(cmd)})")
        proc = subprocess.Popen(
            cmd,
            stdout=log_file,
            stderr=log_file,
            text=True,
            env={**os.environ, "MODE": MODE, "PYTHONUNBUFFERED": "1"}
        )
        self.processes[name] = {"proc": proc, "log_file": log_file}

    def monitor(self):
        logger.info("🛡️ Local Supervisor Active. Monitoring 3 core services...")
        
        for name in SERVICES:
            self.start_service(name)

        try:
            while True:
                for name, data in self.processes.items():
                    proc = data["proc"]
                    
                    # Check if process is still running
                    if proc.poll() is not None:
                        logger.error(f"❌ Service {name} has CRASHED (Exit Code: {proc.returncode})")
                        self._handle_crash(name)
                
                time.sleep(3) # Watchdog interval
        except KeyboardInterrupt:
            logger.warning("🛑 Supervisor shutting down. Terminating all services...")
            self.shutdown()

    def _handle_crash(self, name):
        stats = self.health_stats[name]
        now = datetime.now()
        
        # Track crash history for rate-limiting
        stats["history"] = [t for t in stats["history"] if t > now - timedelta(hours=1)]
        stats["history"].append(now)
        stats["restarts"] += 1
        
        if len(stats["history"]) > 10:
            logger.critical(f"🔥 FATAL: Service {name} is stuck in a crash loop (>10 in 1hr). Manual intervention required.")
            # We don't exit the supervisor, but we stop restarting THIS service
            del self.processes[name]
            return

        logger.info(f"🔄 Restarting {name} in 3 seconds... (Restart #{stats['restarts']})")
        time.sleep(3)
        self.processes[name]["log_file"].close()
        self.start_service(name)

    def shutdown(self):
        for name, data in self.processes.items():
            data["proc"].terminate()
            data["log_file"].close()
        sys.exit(0)

if __name__ == "__main__":
    supervisor = LocalSupervisor()
    supervisor.monitor()
