"""
scrapers/understat_scraper.py
Scraper for xG data from Understat.
"""

import json
import re
import httpx
from bs4 import BeautifulSoup
from loguru import logger
from typing import List, Dict, Optional

UNDERSTAT_BASE = "https://understat.com"

async def fetch_understat_match_xg(match_id_or_url: str) -> Dict:
    """
    Fetch xG data for a specific match from Understat.
    """
    url = match_id_or_url
    if not url.startswith("http"):
        url = f"{UNDERSTAT_BASE}/match/{match_id_or_url}"
    
    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        
    soup = BeautifulSoup(resp.text, 'html.parser')
    scripts = soup.find_all('script')
    
    # Understat stores data in JSON blobs within script tags
    # shotsData, roamingData, etc.
    xg_data = {}
    for s in scripts:
        if s.string and 'shotsData' in s.string:
            # Extract JSON string
            match = re.search(r"JSON\.parse\('(.+)'\)", s.string)
            if match:
                data_str = match.group(1)
                # Decode escape sequences
                data_str = data_str.encode('utf-8').decode('unicode_escape')
                xg_data = json.loads(data_str)
                break
                
    return xg_data

async def fetch_understat_league_results(league: str, season: str = "2024") -> List[Dict]:
    """
    Fetch all results/xG for a league season.
    Leagues: EPL, La_Liga, Bundesliga, Serie_A, Ligue_1, RFPL
    """
    url = f"{UNDERSTAT_BASE}/league/{league}/{season}"
    
    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        
    soup = BeautifulSoup(resp.text, 'html.parser')
    scripts = soup.find_all('script')
    
    results_data = []
    for s in scripts:
        if s.string and 'datesData' in s.string:
            match = re.search(r"JSON\.parse\('(.+)'\)", s.string)
            if match:
                data_str = match.group(1)
                data_str = data_str.encode('utf-8').decode('unicode_escape')
                results_data = json.loads(data_str)
                break
                
    return results_data

def calculate_match_xg_totals(shots_data: Dict) -> Dict:
    """
    Helper to sum xG from individual shots.
    """
    totals = {"home": 0.0, "away": 0.0}
    for side in ["h", "a"]:
        for shot in shots_data.get(side, []):
            totals[side if side == "h" else "away"] += float(shot.get("xG", 0))
    return totals
