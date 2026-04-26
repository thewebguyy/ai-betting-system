"""
backtest/run_backtest.py
Orchestrator for the AI Betting System Backtester.
"""

import sys
import os
import httpx
import pandas as pd
from loguru import logger

# Add project root to path
sys.path.append(os.getcwd())

from backtest.data_loader import DataLoader
from backtest.model_runner import BacktestModelRunner
from backtest.simulator import BettingSimulator
from backtest.metrics import calculate_metrics

def download_sample_data(data_dir: str):
    """Downloads sample data from football-data.co.uk if missing."""
    # EPL 23/24 and 22/23 for a good test window
    files = [
        ("E0", "2324"),
        ("E0", "2223")
    ]
    
    for league, season in files:
        filename = f"{league}_{season}.csv"
        filepath = os.path.join(data_dir, filename)
        if not os.path.exists(filepath):
            url = f"https://www.football-data.co.uk/mmz4281/{season}/{league}.csv"
            logger.info(f"Downloading {url}...")
            try:
                with httpx.Client() as client:
                    resp = client.get(url)
                    resp.raise_for_status()
                    with open(filepath, 'wb') as f:
                        f.write(resp.content)
            except Exception as e:
                logger.error(f"Failed to download {url}: {e}")

async def run_backtest(leagues: list, seasons: list):
    data_dir = "backtest/data"
    if not os.path.exists(data_dir):
        os.makedirs(data_dir)
        
    download_sample_data(data_dir)
    
    loader = DataLoader(data_dir)
    runner = BacktestModelRunner()
    simulator = BettingSimulator(initial_bankroll=1000.0, kelly_fraction=0.25)
    
    # We combine all matches into one timeline
    all_matches = []
    for lg in leagues:
        df = loader.merge_seasons(lg, seasons)
        if not df.empty:
            all_matches.append(df)
            
    if not all_matches:
        logger.error("No data available to backtest.")
        return
        
    full_timeline = pd.concat(all_matches).sort_values('date').reset_index(drop=True)
    full_timeline = full_timeline.tail(50)
    
    logger.info(f"🚀 Starting backtest on {len(full_timeline)} matches...")
    
    for i, (_, row) in enumerate(full_timeline.iterrows()):
        if i % 10 == 0:
            logger.info(f"Processing match {i}/{len(full_timeline)}...")
        match_dict = row.to_dict()
        
        # 1. Predict (uses current model state)
        preds = runner.predict_match(match_dict['home_team'], match_dict['away_team'])
        
        # 2. Simulate Bet
        simulator.process_match(match_dict, preds)
        
        # 3. Update Model State (learn from result)
        runner.update_state(
            match_dict['home_team'], 
            match_dict['away_team'], 
            match_dict['home_goals'], 
            match_dict['away_goals']
        )

    # Output Results
    history_df = simulator.get_history_df()
    metrics = calculate_metrics(history_df, 1000.0)
    
    print("\n" + "="*40)
    print("      BACKTEST PERFORMANCE SUMMARY")
    print("="*40)
    for k, v in metrics.items():
        print(f"{k:<20}: {v}")
    print("="*40)
    
    # Save detailed log
    if not history_df.empty:
        log_path = "backtest/backtest_results.csv"
        history_df.to_csv(log_path, index=False)
        logger.info(f"Detailed bet log saved to {log_path}")

if __name__ == "__main__":
    import asyncio
    # Running EPL for the last two seasons
    asyncio.run(run_backtest(['E0'], ['2223', '2324']))
