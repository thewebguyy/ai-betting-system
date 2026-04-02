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

def generate_edge_hypotheses_report():
    """Step 3: Generate the statistical edge hypotheses report"""
    try:
        from scripts.pseudo_execution import run_pseudo_execution_workflow
        hypotheses = run_pseudo_execution_workflow()
    except Exception as e:
        logger.error(f"Error running pseudo_execution: {e}")
        return

    report_file = "reports/ranked_edge_hypotheses.md"
    os.makedirs(os.path.dirname(report_file), exist_ok=True)
    
    md = f"# 🧪 Ranked Market Edge Hypotheses\n"
    md += f"Generated: {datetime.utcnow().isoformat()}\n\n"
    
    if not hypotheses:
        md += "No actionable hypotheses discovered yet. Continue collecting lag and CLV data.\n"
        with open(report_file, "w", encoding="utf-8") as f:
            f.write(md)
        return
        
    def calculate_score(h):
        sample = h.get('sample_size', 0)
        mean_clv = h.get('mean_clv', 0.0)
        p_val = h.get('p_value', 1.0)
        
        if sample < 2 or mean_clv <= 0:
            return 0.0
            
        # Score combining effect size, confidence and sample sizing
        confidence_factor = max(0, (0.05 - p_val) / 0.05) if p_val < 0.05 else 0
        effect_factor = mean_clv * 100 # percentage points
        sample_factor = np.log10(max(10, sample)) # log scaling for stability
        
        if p_val > 0.05:
            # penalize if not significant, but keep score proportional to what it showed
            return (mean_clv * 10) * np.log10(max(2, sample)) / (p_val + 1)
            
        return effect_factor * confidence_factor * sample_factor

    # Sort hypotheses by score descending
    hypotheses.sort(key=calculate_score, reverse=True)
        
    for index, hyp in enumerate(hypotheses, 1):
        score = calculate_score(hyp)
        md += f"## {index}. {hyp['id']}: {hyp['description']}\n"
        md += f"- **Target Bookmaker:** {hyp['bookmaker']} (Avg Lag: {hyp.get('avg_lag_seconds', 0.0):.1f}s, Events: {hyp.get('frequency', 0)})\n"
        md += f"- **Sample Size (Pseudo-Bets):** {hyp.get('sample_size', 0)}\n"
        
        if hyp.get('sample_size', 0) > 0:
            mean_clv = hyp['mean_clv']
            std_clv = hyp['std_clv']
            p_val = hyp['p_value']
            
            ci_lower = mean_clv - 1.96 * (std_clv / np.sqrt(hyp['sample_size'])) if hyp['sample_size'] > 1 else mean_clv
            ci_upper = mean_clv + 1.96 * (std_clv / np.sqrt(hyp['sample_size'])) if hyp['sample_size'] > 1 else mean_clv
            
            md += f"- **Mean CLV:** {mean_clv:+.4f} (95% CI: [{ci_lower:+.4f}, {ci_upper:+.4f}])\n"
            md += f"- **Standard Deviation:** {std_clv:.4f}\n"
            md += f"- **P-Value:** {p_val:.4f}\n"
            md += f"- **Edge Confidence Score:** {score:.2f}\n"
            
            if p_val < 0.05 and mean_clv > 0.02 and hyp['sample_size'] >= 30:
                recommendation = "🟢 **Worthy of live testing** (Significant positive edge and stable sample)"
            elif p_val < 0.05 and mean_clv > 0.01:
                recommendation = "🟡 **Collect more data** (Significant but small edge or small sample size)"
            else:
                recommendation = "🔴 **Discard** (Edge not statistically solid or negative)"
                
            md += f"- **Recommendation:** {recommendation}\n\n"
        else:
            md += f"- *No pseudo-bets simulated due to missing CLV observations for this market.*\n\n"
            
    with open(report_file, "w", encoding="utf-8") as f:
        f.write(md)
    logger.info(f"Ranked edge hypotheses report generated: {report_file}")

if __name__ == "__main__":
    generate_clv_report()
    generate_lag_report()
    generate_edge_hypotheses_report()
