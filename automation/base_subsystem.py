"""
automation/base_subsystem.py
Base class for all event-driven subsystems.
"""

import time
import os
from loguru import logger
from automation.event_bus import EventBus

class BaseSubsystem:
    def __init__(self, name: str):
        self.name = name
        self.bus = EventBus()
        self.last_event_id = 0
        self.execution_mode = os.environ.get("EXECUTION_MODE", "PAPER") # Hard Guardrail
        
        # Configure correlation logging
        logger.configure(extra={"subsystem": self.name})
        
    def log(self, message: str, event_id: str = "N/A", level: str = "INFO"):
        log_msg = f"[{self.name}] {message}"
        if event_id != "N/A":
            logger.bind(event_id=event_id).log(level, log_msg)
        else:
            logger.log(level, log_msg)

    def heartbeat(self):
        self.bus.heartbeat(self.name)

    def run(self):
        """Main loop to be implemented by child classes."""
        raise NotImplementedError
