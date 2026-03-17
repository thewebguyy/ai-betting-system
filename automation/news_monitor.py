"""
automation/news_monitor.py
Monitors team news and injuries.
"""

from loguru import logger
from sqlalchemy import select
from backend.database import AsyncSessionLocal
from backend.models import Match
from scrapers.data_fetch import fetch_injuries
from datetime import datetime, timedelta

async def monitor_team_news():
    """
    Poll injuries for matches starting in the next 48 hours.
    """
    now = datetime.utcnow()
    cutoff = now + timedelta(hours=48)
    
    async with AsyncSessionLocal() as db:
        stmt = select(Match).where(
            Match.status == "scheduled",
            Match.match_date >= now,
            Match.match_date <= cutoff
        )
        result = await db.execute(stmt)
        matches = result.scalars().all()
        
        for match in matches:
            try:
                # API-Football injuries endpoint
                # Match.api_id could be a string like 'epl-123' if from other sources
                if not match.api_id or not str(match.api_id).isdigit():
                    logger.debug(f"Skipping injuries for Match {match.id}: non-numeric api_id '{match.api_id}'")
                    continue

                raw_injuries = await fetch_injuries(int(match.api_id))
                
                # Update match
                home_inj = [i['player']['name'] for i in raw_injuries if i.get('team', {}).get('id') == match.home_team_id]
                away_inj = [i['player']['name'] for i in raw_injuries if i.get('team', {}).get('id') == match.away_team_id]
                
                match.home_injuries = ",".join(home_inj)
                match.away_injuries = ",".join(away_inj)
                
                logger.info(f"Injuries updated for Match {match.id}: {len(home_inj)}H, {len(away_inj)}A")
            except Exception as e:
                logger.error(f"News monitor error for Match {match.id}: {e}")

        
        await db.commit()
