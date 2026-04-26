import time
import random
from automation.base_subsystem import BaseSubsystem

class AlphaDetector(BaseSubsystem):
    def __init__(self):
        super().__init__("ALPHA")

    def run(self):
        self.log("Alpha Detector ONLINE. Polling for market shocks...")
        
        while True:
            self.heartbeat()
            
            # Simulate Detection
            if random.random() < 0.1:
                match_id = f"M_{random.randint(1000, 9999)}"
                alpha = random.uniform(0.04, 0.08)
                
                payload = {
                    "match_id": match_id,
                    "alpha": alpha,
                    "ts_detected": time.time()
                }
                
                # EMIT SIGNAL_DETECTED
                event_id = self.bus.emit("SIGNAL_DETECTED", payload, self.name)
                self.log(f"SIGNAL EMITTED: {match_id} (Alpha: {alpha:.2%})", event_id)
            
            time.sleep(5)

if __name__ == "__main__":
    AlphaDetector().run()
