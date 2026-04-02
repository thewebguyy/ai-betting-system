import sys
import pandas as pd
import numpy as np
import json
import os
from scipy import stats
from datetime import datetime
from typing import List, Dict, Any, Tuple

# Fix Windows encoding for terminal output
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# Constants
CLV_LOG_FILE = "logs/clv_observations.jsonl"
LAG_LOG_FILE = "logs/lag_analysis.jsonl"
REPORT_FILE = "reports/statistical_edge_report.md"
BOOTSTRAP_ITERATIONS = 10000
RANDOM_SEED = 42

def load_data(file_path: str) -> pd.DataFrame:
    """Load JSONL data into a DataFrame."""
    if not os.path.exists(file_path):
        return pd.DataFrame()
    
    data = []
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    data.append(json.loads(line))
    except Exception as e:
        print(f"Error loading {file_path}: {e}")
        return pd.DataFrame()
    
    return pd.DataFrame(data)

def get_report_conclusion(
    n_total: int,
    n_pinnacle: int,
    p_value: float,
    ci_lower: float,
    mean_clv: float
) -> str:
    """Determine the final verdict based on decision rules."""
    if n_total < 50:
        return "Inconclusive --- insufficient data"
    
    # 95% CI entirely above 0 is the strongest evidence
    if ci_lower > 0 and p_value < 0.05:
        return "Statistically significant edge detected"
    
    if p_value >= 0.05:
        return "No statistical evidence of edge"
    
    return "Inconclusive --- insufficient data"

def run_evaluation():
    os.makedirs("reports", exist_ok=True)
    
    # Step 1: Load Data
    full_df = load_data(CLV_LOG_FILE)
    
    if full_df.empty:
        generate_empty_report("No data found in clv_observations.jsonl")
        return

    # Filter Pinnacle only
    pinnacle_df = pd.DataFrame()
    if "closing_source" in full_df.columns:
        pinnacle_df = full_df[full_df["closing_source"] == "pinnacle"].copy()
    
    datasets = {
        "full_dataset": full_df,
        "pinnacle_only": pinnacle_df
    }

    report_content = "# CLV Statistical Edge Report\n\n"
    report_content += f"*Generated at: {datetime.utcnow().isoformat()}Z*\n\n"

    final_verdict = ""

    for name, df in datasets.items():
        if df.empty and name == "pinnacle_only":
            continue
            
        report_content += f"## Dataset: {name}\n"
        n = len(df)
        report_content += f"- **Sample Size**: {n}\n"
        
        if n < 100 and name == "pinnacle_only":
            report_content += "> [!WARNING]\n"
            report_content += "> Low-confidence dataset (sub-100 samples from Pinnacle).\n\n"
        
        if n < 5:
            report_content += "Insufficient data for statistical testing.\n\n"
            if name == "full_dataset":
                final_verdict = "Inconclusive --- insufficient data"
            continue

        # Step 2: Metric Standardization
        if "CLV_delta_prob" in df.columns:
            df["clv_prob"] = df["CLV_delta_prob"]
        elif "model_odds" in df.columns and "closing_odds" in df.columns:
            df["clv_prob"] = (1 / df["model_odds"]) - (1 / df["closing_odds"])
        else:
            report_content += "Missing required CLV columns (CLV_delta_prob or model_odds/closing_odds).\n\n"
            continue
        
        # Drop NaNs
        df = df.dropna(subset=["clv_prob"])
        n = len(df)
        if n < 5:
            report_content += "Insufficient valid samples after cleaning.\n\n"
            continue

        # Step 3: Core Statistics
        mean_clv = df["clv_prob"].mean()
        median_clv = df["clv_prob"].median()
        std_clv = df["clv_prob"].std()
        skew_clv = df["clv_prob"].skew()

        report_content += "### Core Statistics (Implied Prob Delta)\n"
        report_content += f"- **Mean CLV**: {mean_clv:+.4f}\n"
        report_content += f"- **Median CLV**: {median_clv:+.4f}\n"
        report_content += f"- **Std Dev**: {std_clv:.4f}\n"
        report_content += f"- **Skewness**: {skew_clv:.4f}\n\n"

        # Step 4: One-Sample T-Test
        t_stat, p_val = stats.ttest_1samp(df["clv_prob"], 0, alternative='greater')
        
        report_content += "### Significance Test (H1: Mean > 0)\n"
        report_content += f"- **T-statistic**: {t_stat:.4f}\n"
        report_content += f"- **P-value**: {p_val:.4e}\n"
        interpretation = "Statistically Significant Edge" if p_val < 0.05 else "No Evidence of Edge"
        report_content += f"- **Interpretation**: {interpretation}\n\n"

        # Step 5: Bootstrap Validation
        np.random.seed(RANDOM_SEED)
        bootstrap_means = []
        for _ in range(BOOTSTRAP_ITERATIONS):
            resample = df["clv_prob"].sample(n=len(df), replace=True)
            bootstrap_means.append(resample.mean())
        
        ci_lower = np.percentile(bootstrap_means, 2.5)
        ci_upper = np.percentile(bootstrap_means, 97.5)
        
        report_content += "### Bootstrap Validation (10k Resamples)\n"
        report_content += f"- **95% Confidence Interval**: [{ci_lower:+.4f}, {ci_upper:+.4f}]\n"
        ci_interpretation = "Strong evidence (entirely > 0)" if ci_lower > 0 else "Inconclusive (crosses 0)"
        report_content += f"- **Conclusion**: {ci_interpretation}\n\n"

        # Step 6: Stability Analysis
        report_content += "### Stability Analysis (Chronological Chunks)\n"
        df = df.copy()
        df['chunk'] = pd.qcut(range(len(df)), min(5, len(df)), labels=range(1, min(6, len(df)+1)))
        chunk_means = df.groupby('chunk', observed=True)['clv_prob'].mean()
        
        report_content += "| Chunk | Mean CLV |\n|---|---|\n"
        for chunk, m in chunk_means.items():
            report_content += f"| {chunk} | {m:+.4f} |\n"
        
        trend = "Stable"
        if len(chunk_means) >= 2:
            first_half = chunk_means.iloc[:len(chunk_means)//2].mean()
            second_half = chunk_means.iloc[-(len(chunk_means)//2):].mean()
            if second_half < first_half - 0.01:
                trend = "Possible Decay Detected"
            elif second_half > first_half + 0.01:
                trend = "Improving Edge Detected"
        report_content += f"\n- **Trend**: {trend}\n\n"

        # Step 7: Outlier Analysis
        report_content += "### Outlier Impact\n"
        threshold = df["clv_prob"].quantile(0.95)
        no_outliers_df = df[df["clv_prob"] <= threshold]
        mean_no_outliers = no_outliers_df["clv_prob"].mean()
        
        report_content += f"- **Mean (Excluding Top 5%)**: {mean_no_outliers:+.4f}\n"
        diff = mean_clv - mean_no_outliers
        report_content += f"- **Sensitivity**: {'High' if diff > 0.01 else 'Low'} (Diff: {diff:.4f})\n\n"

        if name == "full_dataset":
            final_verdict = get_report_conclusion(n, len(pinnacle_df), p_val, ci_lower, mean_clv)

    # Step 8: Lag Correlation
    lag_df = load_data(LAG_LOG_FILE)
    if not lag_df.empty and not full_df.empty:
        report_content += "## Lag Correlation Analysis\n"
        if "match_id" in full_df.columns and "match_id" in lag_df.columns:
            merged = pd.merge(full_df, lag_df, on="match_id")
            if not merged.empty and "lag_seconds" in merged.columns and "clv_prob" in merged.columns:
                corr, p_corr = stats.pearsonr(merged["lag_seconds"], merged["clv_prob"])
                report_content += f"- **Pearson Correlation (Lag vs CLV)**: {corr:.4f} (p={p_corr:.4f})\n"
                report_content += f"- **Finding**: {'Correlation found' if p_corr < 0.05 else 'No significant correlation'}\n\n"
    
    report_content += "---\n\n"
    report_content += f"### FINAL VERDICT\n"
    report_content += f"**{final_verdict}**\n"

    with open(REPORT_FILE, "w", encoding="utf-8") as f:
        f.write(report_content)
    
    print(f"Report generated at {REPORT_FILE}")

def generate_empty_report(reason: str):
    content = "# CLV Statistical Edge Report\n\n"
    content += f"**Status**: Inconclusive\n\n"
    content += f"**Reason**: {reason}\n\n"
    content += "---\n\n"
    content += "### FINAL VERDICT\n"
    content += "**Inconclusive --- insufficient data**\n"
    try:
        with open(REPORT_FILE, "w", encoding="utf-8") as f:
            f.write(content)
        print("Empty report generated.")
    except Exception as e:
        # Final fallback: print to stdout if file write fails
        print(content)
        print(f"Error writing report file: {e}")

if __name__ == "__main__":
    run_evaluation()
