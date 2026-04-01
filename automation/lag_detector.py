"""
automation/lag_detector.py
Analyzes odds history to detect lag between sharp bookmakers (Pinnacle) 
and local bookmakers (SportyBet, Bet9ja).
"""

import json
import os
from datetime import datetime, timedelta
from loguru import logger
from sqlalchemy import select, and_
from backend.database import AsyncSessionLocal
from backend.models import OddsHistory, Match
from backend.config import get_settings

settings = get_settings()

async def run_lag_analysis(match_id: int):
    """
    Compare Pinnacle (sharp) odds vs local books (SportyBet, Bet9ja) for a specific match.
    """
    async with AsyncSessionLocal() as db:
        # 1. Get all odds for this match from relevant bookmakers
        sharp_bookie = "pinnacle"
        local_bookies = ["sportybet", "bet9ja"]
        
        stmt = (
            select(OddsHistory)
            .where(
                OddsHistory.match_id == match_id,
                OddsHistory.bookmaker.in_([sharp_bookie] + local_bookies)
            )
            .order_by(OddsHistory.fetched_at.asc())
        )
        result = await db.execute(stmt)
        all_odds = result.scalars().all()
        
        if not all_odds:
            return
            
        # Organize odds by bookmaker and market
        # bm_market_odds[bookmaker][market] = [OddsHistory, ...]
        bm_market_odds = {}
        for o in all_odds:
            if o.bookmaker not in bm_market_odds:
                bm_market_odds[o.bookmaker] = {}
            market = o.market or "1X2"
            if market not in bm_market_odds[o.bookmaker]:
                bm_market_odds[o.bookmaker][market] = []
            bm_market_odds[o.bookmaker][market].append(o)
            
        if sharp_bookie not in bm_market_odds:
            return
            
        for local_bm in local_bookies:
            if local_bm not in bm_market_odds:
                continue
                
            for market, sharp_list in bm_market_odds[sharp_bookie].items():
                if market not in bm_market_odds[local_bm]:
                    continue
                    
                local_list = bm_market_odds[local_bm][market]
                
                # Detect changes in Sharp odds
                for i in range(1, len(sharp_list)):
                    s_prev = sharp_list[i-1]
                    s_curr = sharp_list[i]
                    
                    # Detect movement (simplified 1X2 change detection)
                    if (s_curr.home_odds != s_prev.home_odds or 
                        s_curr.draw_odds != s_prev.draw_odds or 
                        s_curr.away_odds != s_prev.away_odds):
                        
                        ts_sharp = s_curr.fetched_at
                        
                        # Find when the local bookie followed
                        # We look for the first change in local_list AFTER ts_sharp
                        follower_change = None
                        prev_local = None
                        
                        # First, find the local odds at or just BEFORE ts_sharp
                        for l_idx, l_odds in enumerate(local_list):
                            if l_odds.fetched_at <= ts_sharp:
                                prev_local = l_odds
                            else:
                                # This is the first local reading AFTER sharp change
                                # Check if it's different from the last local reading
                                if prev_local and (l_odds.home_odds != prev_local.home_odds or 
                                                 l_odds.draw_odds != prev_local.draw_odds or 
                                                 l_odds.away_odds != prev_local.away_odds):
                                    follower_change = l_odds
                                    break
                                prev_local = l_odds
                                
                        if follower_change:
                            lag = (follower_change.fetched_at - ts_sharp).total_seconds()
                            
                            # Only record if it's a positive lag (indicates following)
                            if lag >= 0:
                                log_entry = {
                                    "match_id": match_id,
                                    "market": market,
                                    "local_bookmaker": local_bm,
                                    "timestamp_sharp_change": ts_sharp.isoformat(),
                                    "timestamp_local_change": follower_change.fetched_at.isoformat(),
                                    "lag_seconds": lag,
                                    "odds_before": {
                                        "home": s_prev.home_odds,
                                        "draw": s_prev.draw_odds,
                                        "away": s_prev.away_odds
                                    },
                                    "odds_after": {
                                        "home": s_curr.home_odds,
                                        "draw": s_curr.draw_odds,
                                        "away": s_curr.away_odds
                                    }
                                }
                                archive_lag(log_entry)

def archive_lag(data: dict):
    """Save lag analysis result to JSONL."""
    os.makedirs(os.path.dirname(settings.lag_log_path), exist_ok=True)
    with open(settings.lag_log_path, "a") as f:
        f.write(json.dumps(data) + "\n")

async def analyze_all_recent_matches():
    """
    Run lag analysis for all matches scheduled or finished in the last 24h.
    """
    async with AsyncSessionLocal() as db:
        now = datetime.utcnow()
        stmt = select(Match.id).where(
            and_(
                Match.match_date >= now - timedelta(days=1),
                Match.match_date <= now + timedelta(days=1)
            )
        )
        result = await db.execute(stmt)
        match_ids = result.scalars().all()
        
        logger.info(f"Running lag analysis for {len(match_ids)} matches…")
        for mid in match_ids:
            await run_lag_analysis(mid)
