"""
scripts/debug_clv_lifecycle.py
Audit script to print 10 random signals with their full validation lifecycle.
Used to verify time integrity and detect data leakage.
"""

import sqlite3
import json
import random
from datetime import datetime

DB_PATH = "data/final_events.db"

def debug_lifecycle():
    print("\n" + "="*80)
    print("      CLV LIFECYCLE AUDIT (10 RANDOM SIGNALS)")
    print("="*80 + "\n")

    try:
        conn = sqlite3.connect(DB_PATH)
        # Fetch VALIDATION_COMPLETE events
        cursor = conn.execute("SELECT payload FROM events WHERE topic = 'VALIDATION_COMPLETE'")
        rows = cursor.fetchall()
        conn.close()

        if not rows:
            print("No validated signals found. Run the Truth Engine first.")
            return

        # Select 10 random samples
        samples = random.sample(rows, min(10, len(rows)))

        for i, row in enumerate(samples, 1):
            data = json.loads(row[0])
            
            ts_det = data.get('ts_detected', 0)
            ts_close = data.get('ts_closing', 0)
            det_dt = datetime.fromtimestamp(ts_det).strftime('%H:%M:%S') if ts_det else "N/A"
            close_dt = datetime.fromtimestamp(ts_close).strftime('%H:%M:%S') if ts_close else "N/A"
            
            is_leakage_free = data.get('is_leakage_free', False)
            clv = data.get('clv', 0)
            status = "WIN (Beats Closing)" if clv > 0 else "LOSS (Market Laggard)"
            
            print(f"[{i}] Match: {data.get('match_id')} | Source: {data.get('source_name')}")
            print(f"    - Detection: {det_dt} (@ {data.get('odds_at_detection'):.2f})")
            print(f"    - Closing:   {close_dt} (@ {data.get('closing_odds', 0):.2f})")
            print(f"    - Integrity: {'PASS' if ts_det < ts_close and is_leakage_free else 'FAIL (LEAKAGE/LEGACY)'}")
            print(f"    - Market:    {status}")
            print(f"    - CLV:       {clv:+.2%} | CAS: {data.get('cas_category')}")
            print("-" * 60)

    except Exception as e:
        print(f"Audit Error: {e}")

    print("\n" + "="*80)

if __name__ == "__main__":
    debug_lifecycle()
