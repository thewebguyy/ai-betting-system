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
                # In a real scenario, match.api_id would be the fixture ID
                raw_injuries = await fetch_injuries(int(match.api_id))
                
                # Update match
                home_inj = [i['player']['name'] for i in raw_injuries if i['team']['id'] == match.home_team_id]
                away_inj = [i['player']['name'] for i in raw_injuries if i['team']['id'] == match.away_team_id]
                
                match.home_injuries = ",".join(home_inj)
                match.away_injuries = ",".join(away_inj)
                
                logger.info(f"Injuries updated for Match {match.id}")
            except Exception as e:
                # logger.error(f"News monitor error for Match {match.id}: {e}")
                pass
        
        await db.commit()
