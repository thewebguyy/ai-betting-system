"""
scripts/generate_research_reports.py
Generates CLV Summary and Lag Analysis reports from JSONL logs.
"""

import json
import os
import numpy as np
from datetime import datetime
from loguru import logger
from backend.config import get_settings

settings = get_settings()

def generate_clv_report():
    """Step 3: CLV Data Quality Validation Report"""
    log_file = settings.clv_log_path
    report_file = "reports/clv_summary.md"
    os.makedirs("reports", exist_ok=True)
    
    if not os.path.exists(log_file):
        logger.warning(f"CLV log file not found: {log_file}")
        return
        
    observations = []
    with open(log_file, "r") as f:
        for line in f:
            if line.strip(): observations.append(json.loads(line))
            
    if not observations:
        logger.warning("No CLV observations found.")
        return
        
    settled = [o for o in observations if o.get("closing_odds") is not None]
    total = len(observations)
    total_settled = len(settled)
    
    pinnacle_count = sum(1 for o in settled if o.get("closing_source") == "pinnacle")
    market_avg_count = total_settled - pinnacle_count
    
    clv_odds = [o["CLV_delta_odds"] for o in settled]
    clv_probs = [o["CLV_delta_prob"] for o in settled]
    
    avg_clv_odds = np.mean(clv_odds) if clv_odds else 0
    median_clv_odds = np.median(clv_odds) if clv_odds else 0
    avg_clv_prob = np.mean(clv_probs) if clv_probs else 0
    
    pinnacle_pct = (pinnacle_count / total_settled * 100) if total_settled > 0 else 0
    
    # Generate Markdown
    md = f"""# 📊 CLV Data Quality Validation Report
Generated: {datetime.utcnow().isoformat()}

## Summary Metrics
* **Total Observations:** {total}
* **Total Settled:** {total_settled}
* **Pinnacle Coverage:** {pinnacle_pct:.1f}% {"✅" if pinnacle_pct >= 50 else "⚠️"}
* **Market Average Fallback:** {market_avg_count}

## CLV Statistics
* **Average CLV (Odds):** {avg_clv_odds:+.3f}
* **Median CLV (Odds):** {median_clv_odds:+.3f}
* **Average CLV (Probability):** {avg_clv_prob:+.4f}

## Decision Rule
{ "✅ **Status:** CLV signal is reliable." if pinnacle_pct >= 50 else "⚠️ **Warning:** CLV signal unreliable due to insufficient sharp market data (< 50% Pinnacle coverage)." }

## CLV Distribution (Binned)
"""
    if clv_odds:
        hist, bins = np.histogram(clv_odds, bins=10)
        for i in range(len(hist)):
            md += f"* {bins[i]:.2f} to {bins[i+1]:.2f}: {'|' * (hist[i] // max(1, total_settled//50))} ({hist[i]})\n"

    with open(report_file, "w") as f:
        f.write(md)
    logger.info(f"CLV report generated: {report_file}")

def generate_lag_report():
    """Step 4: Market Lag Analysis Report"""
    log_file = settings.lag_log_path
    report_file = "reports/lag_summary.md"
    os.makedirs("reports", exist_ok=True)
    
    if not os.path.exists(log_file):
        logger.warning(f"Lag log file not found: {log_file}")
        return
        
    lags = []
    with open(log_file, "r") as f:
        for line in f:
            if line.strip(): lags.append(json.loads(line))
            
    if not lags:
        logger.warning("No lag data found.")
        return
        
    lag_values = [l["lag_seconds"] for l in lags]
    
    avg_lag = np.mean(lag_values)
    median_lag = np.median(lag_values)
    p90_lag = np.percentile(lag_values, 90)
    
    gt_60 = sum(1 for l in lag_values if l > 60) / len(lags) * 100
    gt_300 = sum(1 for l in lag_values if l > 300) / len(lags) * 100
    gt_900 = sum(1 for l in lag_values if l > 900) / len(lags) * 100
    
    md = f"""# ⏱️ Market Lag Analysis Report
Generated: {datetime.utcnow().isoformat()}

## Core Metrics
* **Total Events Captured:** {len(lags)}
* **Average Lag:** {avg_lag:.1f} seconds
* **Median Lag:** {median_lag:.1f} seconds
* **90th Percentile Lag:** {p90_lag:.1f} seconds

## Lag Distribution
* **Events with > 60s lag:** {gt_60:.1f}%
* **Events with > 300s lag:** {gt_300:.1f}%
* **Events with > 900s lag:** {gt_900:.1f}%

## Breakdown by Bookmaker
| Bookmaker | Avg Lag (s) | Median Lag (s) | Count |
|-----------|-------------|---------------|-------|
"""
    # Breakdown by bookmaker
    bms = set(l["local_bookmaker"] for l in lags)
    for bm in bms:
        bm_lags = [l["lag_seconds"] for l in lags if l["local_bookmaker"] == bm]
        md += f"| {bm} | {np.mean(bm_lags):.1f} | {np.median(bm_lags):.1f} | {len(bm_lags)} |\n"

    with open(report_file, "w") as f:
        f.write(md)
    logger.info(f"Lag report generated: {report_file}")

if __name__ == "__main__":
    generate_clv_report()
    generate_lag_report()
