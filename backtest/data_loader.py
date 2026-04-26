"""
backtest/data_loader.py
Handles loading and normalization of historical football data from football-data.co.uk.
"""

import pandas as pd
import os
from typing import List, Dict, Optional
from loguru import logger

# Column mapping for football-data.co.uk CSVs
COLUMNS = {
    'Date': 'date',
    'HomeTeam': 'home_team',
    'AwayTeam': 'away_team',
    'FTHG': 'home_goals',
    'FTAG': 'away_goals',
    'FTR': 'result',
    'B365H': 'odds_h',
    'B365D': 'odds_d',
    'B365A': 'odds_a',
    'B365>2.5': 'odds_over',
    'B365<2.5': 'odds_under'
}

class DataLoader:
    def __init__(self, data_dir: str = "backtest/data"):
        self.data_dir = data_dir
        if not os.path.exists(self.data_dir):
            os.makedirs(self.data_dir)

    def load_league_season(self, league: str, season: str) -> pd.DataFrame:
        """
        Loads data for a specific league and season.
        Example: league='E0' (EPL), season='2324' (2023-2024)
        """
        filename = f"{league}_{season}.csv"
        filepath = os.path.join(self.data_dir, filename)
        
        # In a real production scenario, we'd fetch from URL if missing
        # url = f"https://www.football-data.co.uk/mmz4281/{season}/{league}.csv"
        
        if not os.path.exists(filepath):
            logger.error(f"Data file missing: {filepath}. Please download it from football-data.co.uk")
            return pd.DataFrame()

        try:
            df = pd.read_csv(filepath)
            # Filter and rename
            existing_cols = [c for c in COLUMNS.keys() if c in df.columns]
            df = df[existing_cols].rename(columns=COLUMNS)
            
            # Convert date
            # football-data.co.uk uses DD/MM/YY or DD/MM/YYYY
            try:
                df['date'] = pd.to_datetime(df['date'], dayfirst=True)
            except:
                df['date'] = pd.to_datetime(df['date'])
                
            df = df.sort_values('date').reset_index(drop=True)
            
            # Clean odds - fill NaN with 1.0 or drop
            df = df.dropna(subset=['odds_h', 'odds_d', 'odds_a', 'result'])
            
            logger.info(f"Loaded {len(df)} matches for {league} {season}")
            return df
        except Exception as e:
            logger.error(f"Error loading {filepath}: {e}")
            return pd.DataFrame()

    def merge_seasons(self, league: str, seasons: List[str]) -> pd.DataFrame:
        """Merges multiple seasons into one continuous timeline."""
        all_dfs = []
        for s in seasons:
            df = self.load_league_season(league, s)
            if not df.empty:
                all_dfs.append(df)
        
        if not all_dfs:
            return pd.DataFrame()
            
        combined = pd.concat(all_dfs).sort_values('date').reset_index(drop=True)
        logger.info(f"Combined total: {len(combined)} matches")
        return combined

def get_data_loader():
    return DataLoader()
