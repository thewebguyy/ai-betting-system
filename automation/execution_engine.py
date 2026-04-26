import time
import os
from automation.base_subsystem import BaseSubsystem

class ExecutionEngine(BaseSubsystem):
    def __init__(self):
        super().__init__("EXECUTOR")

    def run(self):
        self.log(f"Execution Engine ONLINE. Mode: {self.execution_mode}")
        
        while True:
            self.heartbeat()
            
            # 1. Listen for SIGNAL_DETECTED
            new_events = self.bus.subscribe("SIGNAL_DETECTED", self.last_event_id)
            
            for eid, event_id, topic, payload_str, source in new_events:
                self.last_event_id = eid
                import json
                payload = json.loads(payload_str)
                
                # 2. Hard Execution Guardrail
                if self.execution_mode == "PAPER":
                    self.log(f"PAPER BET: Simulating entry for {payload['match_id']}", event_id)
                elif self.execution_mode == "LIVE":
                    # Real execution logic would go here
                    self.log(f"LIVE BET: Executing REAL trade for {payload['match_id']}", event_id, "WARNING")
                
                # EMIT EXECUTION_COMPLETE
                self.bus.emit("EXECUTION_COMPLETE", {"match_id": payload['match_id'], "mode": self.execution_mode}, self.name)
            
            time.sleep(2)

if __name__ == "__main__":
    ExecutionEngine().run()
