"""
backtest/clv_analyzer.py
Professional CLV diagnostic layer for betting market efficiency analysis.
"""

import pandas as pd
import numpy as np
from loguru import logger

def analyze_clv(history_df: pd.DataFrame) -> dict:
    """
    Analyzes Closing Line Value across different segments.
    """
    if history_df.empty:
        return {"error": "No data to analyze."}

    # Ensure CLV is calculated: (Entry / Closing) - 1
    # Industry standard: > 0 means you beat the line.
    
    # Segment: Favorites (Prob > 50%), Underdogs (Prob < 40%), and Draws
    df = history_df.copy()
    
    def get_segment(row):
        if row['market'] == 'draw':
            return 'Draws'
        if row['prob'] > 0.50:
            return 'Favorites'
        if row['prob'] < 0.40:
            return 'Underdogs'
        return 'Middle'

    df['segment'] = df.apply(get_segment, axis=1)
    
    summary = {}
    
    # 1. Overall Metrics
    overall_clv = df['clv'].mean() * 100
    weighted_clv = (df['clv'] * df['stake_amt']).sum() / df['stake_amt'].sum() * 100 if df['stake_amt'].sum() > 0 else 0
    
    summary['overall'] = {
        'avg_clv_pct': round(overall_clv, 2),
        'weighted_clv_pct': round(weighted_clv, 2),
        'total_bets': len(df)
    }
    
    # 2. Segmented Metrics
    segments = df.groupby('segment').agg(
        n_bets=('clv', 'count'),
        avg_clv=('clv', 'mean'),
        win_rate=('is_win', 'mean'),
        roi=('profit', lambda x: (x.sum() / df.loc[x.index, 'stake_amt'].sum()) * 100 if df.loc[x.index, 'stake_amt'].sum() > 0 else 0)
    ).reset_index()
    
    summary['segmented'] = segments.to_dict('records')
    
    # 3. Market Edge Flagging
    summary['diagnostics'] = []
    
    if overall_clv < 0:
        summary['diagnostics'].append("⚠️ FLAG: No Market Edge. The model is consistently betting on lines that move AGAINST it.")
    elif overall_clv > 0 and (df['profit'].sum() < 0):
        summary['diagnostics'].append("💡 FLAG: Positive CLV but Negative ROI. Likely short-term variance or a staking/bankroll issue.")
    elif overall_clv > 2.0:
        summary['diagnostics'].append("🚀 FLAG: Strong Market Edge. Model is beating the closing line by >2% on average.")

    return summary

def print_clv_report(report: dict):
    if 'error' in report:
        print(f"CLV Analysis Error: {report['error']}")
        return

    print("\n" + "="*50)
    print("      CLOSING LINE VALUE (CLV) DIAGNOSTICS")
    print("="*50)
    o = report['overall']
    print(f"Overall Avg CLV    : {o['avg_clv_pct']}%")
    print(f"Weighted CLV       : {o['weighted_clv_pct']}%")
    print(f"Total Evaluated    : {o['total_bets']} bets")
    print("-" * 50)
    
    print(f"{'SEGMENT':<12} | {'BETS':<5} | {'CLV %':<8} | {'ROI %':<8} | {'WIN %':<8}")
    print("-" * 50)
    for s in report['segmented']:
        print(f"{s['segment']:<12} | {s['n_bets']:<5} | {s['avg_clv']*100:>7.2f}% | {s['roi']:>7.2f}% | {s['win_rate']*100:>7.2f}%")
    
    print("-" * 50)
    for d in report['diagnostics']:
        print(d)
    print("="*50)
