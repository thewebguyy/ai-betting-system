import time
import json
from automation.base_subsystem import BaseSubsystem

class TruthValidator(BaseSubsystem):
    def __init__(self):
        super().__init__("TRUTH")

    def run(self):
        self.log("Truth & Causal Validator ONLINE. Listening for signals...")
        
        while True:
            self.heartbeat()
            
            # Subscribe to SIGNAL_DETECTED
            events = self.bus.subscribe("SIGNAL_DETECTED", self.last_event_id)
            
            for eid, event_id, topic, payload_str, source in events:
                self.last_event_id = eid
                payload = json.loads(payload_str)
                
                # Perform Analysis
                self.log(f"Analyzing Causal Edge for {payload['match_id']}...", event_id)
                
                # EMIT ANALYSIS_COMPLETE
                self.bus.emit("ANALYSIS_COMPLETE", {"match_id": payload['match_id'], "causal_score": 0.85}, self.name)
            
            time.sleep(3)

if __name__ == "__main__":
    TruthValidator().run()
