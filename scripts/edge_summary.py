"""
scripts/edge_summary.py
Scientific Summary of System Alpha.
Run this to see the truth-layer performance.
"""

import sqlite3
import json
import os
import pandas as pd
from loguru import logger

DB_PATH = "data/final_events.db"

def generate_report():
    if not os.path.exists(DB_PATH):
        print("Error: No data found. Run the system first.")
        return

    print("\n" + "="*50)
    print("      AI BETTING EDGE VALIDATION SUMMARY")
    print("="*50 + "\n")

    conn = sqlite3.connect(DB_PATH)
    # Fetch all validation events
    query = "SELECT payload FROM events WHERE topic = 'VALIDATION_COMPLETE'"
    rows = conn.execute(query).fetchall()
    conn.close()

    if not rows:
        print("No validated signals found yet. Waiting for market closing data...")
        return

    # Parse payloads
    all_data = [json.loads(r[0]) for r in rows]
    total_found = len(all_data)
    
    # REQUIREMENT: Exclude contaminated (historical) data
    df = pd.DataFrame(all_data)
    if 'is_leakage_free' in df.columns:
        df_clean = df[df['is_leakage_free'] == True].copy()
    else:
        df_clean = pd.DataFrame()
        
    excluded_count = total_found - len(df_clean)
    
    if df_clean.empty:
        print(f"No clean validation signals found. (Excluded {excluded_count} legacy signals)")
        return

    df = df_clean
    df['ts'] = pd.to_datetime(df['timestamp_validated'], unit='s')

    # 1. Total Stats
    total_signals = len(df)
    avg_clv = df['clv'].mean()
    median_clv = df['clv'].median()
    pos_clv_pct = (df['clv'] > 0).sum() / total_signals
    neg_clv_count = (df['clv'] <= 0).sum()
    
    # CLV Distribution
    clv_min = df['clv'].min()
    clv_max = df['clv'].max()
    clv_std = df['clv'].std()

    # 2. Sparsity Check (Signals per hour)
    if total_signals > 1:
        time_span_hours = (df['ts'].max() - df['ts'].min()).total_seconds() / 3600
        signals_per_hour = total_signals / max(time_span_hours, 0.1)
    else:
        signals_per_hour = 0

    # 3. CAS Classification Stats
    cas_counts = df['cas_category'].value_counts(normalize=True)
    avg_cas_lead = (df['cas_category'] == 'LEAD').mean()

    # 4. Source Breakdown
    if 'source_name' not in df.columns:
        df['source_name'] = 'UNKNOWN'
    else:
        df['source_name'] = df['source_name'].fillna('UNKNOWN')
        
    source_stats = df.groupby('source_name')['clv'].agg(['mean', 'count']).rename(columns={'mean': 'avg_clv', 'count': 'signals'})

    # 5. Output Report
    print(f"Total Signals Validated: {total_signals} (Excluded {excluded_count} legacy)")
    print(f"Signals Per Hour:       {signals_per_hour:.2f}")
    print(f"Average CLV:            {avg_clv:.2%}")
    print(f"Median CLV:             {median_clv:.2%}")
    print(f"Positive CLV Rate:      {pos_clv_pct:.1%}")
    print(f"Negative CLV Count:     {neg_clv_count}")
    print("-" * 40)
    print(f"CLV Distribution:       Min: {clv_min:.2%} | Max: {clv_max:.2%} | Std: {clv_std:.4f}")
    print("-" * 40)
    print("Causal Classification (CAS):")
    for cat, pct in cas_counts.items():
        print(f"  {cat:12}: {pct:.1%}")
    
    print("-" * 40)
    print("CLV by Source:")
    print(source_stats.to_string())
    
    print("\n" + "="*50)
    
    # Requirement 6: Early Warning System
    if avg_clv < 0:
        print("ALERT: EDGE NOT PRESENT")
    if avg_cas_lead < 0.3:
        print("ALERT: SYSTEM IS LAGGING MARKET")

    # Requirement 5: Warning Flags & Sanity Checks
    warnings = []
    if avg_clv < 0:
        warnings.append("CRITICAL: Negative Average CLV. System is losing to the market.")
    if avg_cas_lead < 0.3:
        warnings.append("WARNING: Low Lead Ratio. Signals may be reactive market-lags.")
    if signals_per_hour < 3.0:
        warnings.append("SPARSITY: Less than 3 signals/hour. Validation set too small for significance.")
    
    # NEW Sanity Checks
    if pos_clv_pct > 0.99 and total_signals > 50:
        warnings.append("UNREALISTIC: 100% Positive CLV rate detected. Check for data leakage or synthetic bias.")
    
    lagging_positive_clv = df[(df['cas_category'] == 'LAG') & (df['clv'] > 0)]
    if not lagging_positive_clv.empty:
        warnings.append(f"INCONSISTENCY: {len(lagging_positive_clv)} lagging signals show positive CLV. Possible leakage.")
    
    if warnings:
        print("SYSTEM HEALTH ALERTS:")
        for w in warnings:
            print(f"  {w}")
    else:
        print("SUCCESS: Strong Lead-Causality and Positive Edge detected.")

    print("="*50)

if __name__ == "__main__":
    generate_report()
