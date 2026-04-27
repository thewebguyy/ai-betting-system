"""
scripts/generate_live_signals.py
Extracts validated, lead-causality signals with positive CLV.
Used for final execution decisioning.
"""

import sqlite3
import json
from datetime import datetime

DB_PATH = "data/final_events.db"

def extract_signals():
    try:
        conn = sqlite3.connect(DB_PATH)
        # Fetch clean validation events
        cursor = conn.execute("SELECT payload FROM events WHERE topic = 'VALIDATION_COMPLETE'")
        rows = cursor.fetchall()
        conn.close()

        valid_signals = []
        for row in rows:
            data = json.loads(row[0])
            
            # Constraints
            is_clean = data.get('is_leakage_free', False)
            clv = data.get('clv', 0)
            cas = data.get('cas_category')
            
            if is_clean and clv > 0.015 and cas == 'LEAD':
                valid_signals.append(data)

        if not valid_signals:
            print("NO EDGE - DO NOT BET")
            return

        # Sort by CLV strength
        valid_signals.sort(key=lambda x: x['clv'], reverse=True)

        print("\n" + "="*80)
        print(f"      LEAD-ALPHA BETTING SIGNALS (Top {min(10, len(valid_signals))})")
        print("="*80 + "\n")

        for i, sig in enumerate(valid_signals[:10], 1):
            ts_str = datetime.fromtimestamp(sig.get('ts_detected', 0)).strftime('%Y-%m-%d %H:%M:%S')
            print(f"[{i}] MATCH: {sig.get('match_id')} | MARKET: {sig.get('market', '1X2')}")
            print(f"    - Odds at Det: {sig.get('odds_at_detection'):.2f}")
            print(f"    - Validated CLV: {sig.get('clv'):+.2%}")
            print(f"    - Timestamp:   {ts_str}")
            print(f"    - Source:      {sig.get('source_name', 'UNKNOWN')}")
            print("-" * 60)

    except Exception as e:
        print(f"Signal Generation Error: {e}")

if __name__ == "__main__":
    extract_signals()
