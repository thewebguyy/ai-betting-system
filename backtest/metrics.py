"""
backtest/metrics.py
Calculates performance metrics for the betting strategy.
"""

import pandas as pd
import numpy as np

def calculate_metrics(df: pd.DataFrame, initial_bankroll: float) -> dict:
    if df.empty:
        return {"error": "No bets placed."}

    total_bets = len(df)
    total_profit = df['profit'].sum()
    roi = (total_profit / df['stake_amt'].sum()) * 100 if df['stake_amt'].sum() > 0 else 0
    win_rate = (df['is_win'].sum() / total_bets) * 100
    expected_win_rate = (df['prob'].mean()) * 100
    
    # Drawdown
    df['cum_profit'] = df['profit'].cumsum() + initial_bankroll
    df['peak'] = df['cum_profit'].cummax()
    df['drawdown'] = (df['cum_profit'] - df['peak']) / df['peak']
    max_drawdown = df['drawdown'].min() * 100
    
    # CLV
    avg_clv = df['clv'].mean() * 100
    
    # Sharpe Ratio (Daily or per-bet approximation)
    # Using 0 as risk-free rate for betting
    returns = df['profit'] / df['stake_amt']
    sharpe = (returns.mean() / returns.std()) * np.sqrt(total_bets) if returns.std() > 0 else 0

    return {
        "Total Bets": total_bets,
        "Total Profit": round(total_profit, 2),
        "ROI (%)": round(roi, 2),
        "Win Rate (%)": round(win_rate, 2),
        "Exp. Win Rate (%)": round(expected_win_rate, 2),
        "Max Drawdown (%)": round(max_drawdown, 2),
        "Avg CLV (%)": round(avg_clv, 2),
        "Sharpe Ratio": round(sharpe, 3),
        "Final Bankroll": round(df['bankroll'].iloc[-1], 2)
    }
