"""
automation/signal_auditor.py
Audits the effectiveness of alpha signals by tracking CLV evolution over time.
"""

import time
import pandas as pd
from typing import Dict, List, Optional
from loguru import logger
from dataclasses import dataclass, asdict

@dataclass
class SignalAuditRecord:
    signal_id: str
    match_id: str
    source_type: str # "news", "social", "odds_move"
    confidence_score: float
    timestamp_detected: float
    odds_at_detection: float
    odds_t_plus_1m: Optional[float] = None
    odds_t_plus_5m: Optional[float] = None
    odds_closing: Optional[float] = None
    clv_at_closing: Optional[float] = None
    classification: str = "PENDING" # "TRUE_EDGE", "NEUTRAL", "FALSE_SIGNAL"

class SignalAuditor:
    def __init__(self, storage_path: str = "backtest/signal_audit.csv"):
        self.storage_path = storage_path
        self.active_audits: Dict[str, SignalAuditRecord] = {}
        self.completed_audits: List[SignalAuditRecord] = []

    def register_signal(self, signal_id: str, match_id: str, source: str, score: float, current_odds: float):
        """Initializes a new audit for a detected signal."""
        record = SignalAuditRecord(
            signal_id=signal_id,
            match_id=match_id,
            source_type=source,
            confidence_score=score,
            timestamp_detected=time.time(),
            odds_at_detection=current_odds
        )
        self.active_audits[signal_id] = record
        logger.info(f"📊 Audit Started: Signal {signal_id} (Odds: {current_odds})")

    def update_snapshot(self, signal_id: str, current_odds: float, elapsed_min: int):
        """Records odds at T+1, T+5 etc."""
        if signal_id not in self.active_audits:
            return

        record = self.active_audits[signal_id]
        if elapsed_min == 1:
            record.odds_t_plus_1m = current_odds
        elif elapsed_min == 5:
            record.odds_t_plus_5m = current_odds

    def finalize_audit(self, signal_id: str, closing_odds: float):
        """Calculates final CLV and classifies the signal."""
        if signal_id not in self.active_audits:
            return

        record = self.active_audits.pop(signal_id)
        record.odds_closing = closing_odds
        
        # CLV = (Entry Odds / Closing Odds) - 1
        # Positive CLV means the market moved IN OUR FAVOR after the signal.
        record.clv_at_closing = (record.odds_at_detection / closing_odds) - 1
        
        if record.clv_at_closing > 0.02:
            record.classification = "TRUE_EDGE"
        elif record.clv_at_closing < -0.01:
            record.classification = "FALSE_SIGNAL"
        else:
            record.classification = "NEUTRAL"

        self.completed_audits.append(record)
        logger.success(f"✅ Audit Finalized: {signal_id} | CLV: {record.clv_at_closing:+.2%} | {record.classification}")
        self._save_to_csv()

    def _save_to_csv(self):
        df = pd.DataFrame([asdict(r) for r in self.completed_audits])
        df.to_csv(self.storage_path, index=False)

    def get_summary_report(self) -> dict:
        if not self.completed_audits:
            return {"error": "No data audited yet."}
            
        df = pd.DataFrame([asdict(r) for r in self.completed_audits])
        
        report = {
            "Total Signals": len(df),
            "True Edge (%)": (df['classification'] == 'TRUE_EDGE').mean() * 100,
            "Avg CLV (%)": df['clv_at_closing'].mean() * 100,
            "Best Source": df.groupby('source_type')['clv_at_closing'].mean().idxmax(),
            "Signal-to-Profit Conversion": (df['clv_at_closing'] > 0).mean() * 100
        }
        return report

# For Demo Purposes: Simulated Audit Run
if __name__ == "__main__":
    auditor = SignalAuditor()
    # Mocking a Lineup Leak signal
    auditor.register_signal("sig_001", "m_123", "news", 90.0, 2.10)
    # Market moves after 1 min
    auditor.update_snapshot("sig_001", 2.05, 1)
    # Market moves more after 5 mins
    auditor.update_snapshot("sig_001", 1.95, 5)
    # Final closing line
    auditor.finalize_audit("sig_001", 1.90)
    
    print("\nSUMMARY REPORT:")
    print(auditor.get_summary_report())
