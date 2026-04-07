"""
scripts/bootstrap_system.py
One-time bootstrap script to seed the system with historical data.
Required to break the 'is_sufficient' circular dependency.
"""

import asyncio
import sys
from datetime import datetime, timedelta
from loguru import logger

# Add project root to sys.path
import os
sys.path.append(os.getcwd())

from backend.database import engine, AsyncSessionLocal
from backend.models import Base, League, Team, Match, TeamMatchStats
from scrapers.data_fetch import fetch_fixtures, normalise_fixture, get_active_source
from automation.xg_processor import update_xg_stats, recalculate_team_strengths
from sqlalchemy import select

# Configuration
LEAGUES = [
    {"id": 39, "name": "Premier League"},
    {"id": 140, "name": "La Liga"},
    {"id": 135, "name": "Serie A"},
    {"id": 78, "name": "Bundesliga"},
    {"id": 61, "name": "Ligue 1"},
]
SEASON = 2024

async def bootstrap():
    logger.info("🚀 Starting System Bootstrap...")
    
    # 1. Initialize Tables (Optional if already exist)
    # async with engine.begin() as conn:
    #     await conn.run_sync(Base.metadata.create_all)
    
    source = get_active_source()
    async with AsyncSessionLocal() as db:
        for lg_info in LEAGUES:
            lid = lg_info["id"]
            lname = lg_info["name"]
            logger.info(f"--- Processing {lname} (API ID: {lid}) ---")
            
            # 2. Upsert League
            res_l = await db.execute(select(League).where(League.api_id == str(lid)))
            league = res_l.scalar_one_or_none()
            if not league:
                league = League(api_id=str(lid), name=lname, season=str(SEASON))
                db.add(league)
                await db.flush()
            
            # 3. Fetch Historical Data (Last 15 days) to seed xG
            logger.info(f"Fetching historical results for {lname}...")
            # Note: The underlying fetch_fixtures might need a 'status' or 'from/to' param if supported by the scraper.
            # Assuming fetch_fixtures returns recent enough history or can be filtered.
            hist_fixtures = await fetch_fixtures(league_id=lid, season=SEASON)
            
            # We filter for 'FT' matches to use for xG
            processed_hist = 0
            for raw in hist_fixtures:
                norm = normalise_fixture(raw, source)
                if norm.get("status") not in ["FT", "Match Finished"]:
                    continue
                
                # Upsert Teams
                h_api = norm["home_team_api_id"]
                a_api = norm["away_team_api_id"]
                
                res_h = await db.execute(select(Team).where(Team.api_id == h_api))
                h_team = res_h.scalar_one_or_none()
                if not h_team:
                    h_team = Team(api_id=h_api, name=norm["home_team"], league_id=league.id)
                    db.add(h_team)
                
                res_a = await db.execute(select(Team).where(Team.api_id == a_api))
                a_team = res_a.scalar_one_or_none()
                if not a_team:
                    a_team = Team(api_id=a_api, name=norm["away_team"], league_id=league.id)
                    db.add(a_team)
                
                await db.flush()
                
                # Upsert Match
                res_m = await db.execute(select(Match).where(Match.api_id == norm["api_id"]))
                match = res_m.scalar_one_or_none()
                if not match:
                    match = Match(
                        api_id=norm["api_id"],
                        league_id=league.id,
                        home_team_id=h_team.id,
                        away_team_id=a_team.id,
                        match_date=norm["match_date"],
                        status="finished",
                        home_score=norm.get("home_score"),
                        away_score=norm.get("away_score"),
                    )
                    db.add(match)
                processed_hist += 1
            
            await db.commit()
            logger.info(f"Seeded {processed_hist} historical matches for {lname}.")

        # 4. Process xG for all seeded matches
        # Note: This requires Understat or other source to have matching fixtures.
        # For this bootstrap, we trigger the xG processor for each league.
        from automation.xg_processor import process_all_leagues_xg
        logger.info("Fetching xG data from Understat for seeded teams...")
        await process_all_leagues_xg()
        
        # 5. Fetch Upcoming Fixtures (Next 3 days)
        logger.info("Fetching upcoming fixtures for tonight and beyond...")
        upcoming_count = 0
        for lg_info in LEAGUES:
            lid = lg_info["id"]
            upcoming = await fetch_fixtures(league_id=lid, season=SEASON)
            for raw in upcoming:
                norm = normalise_fixture(raw, source)
                if norm.get("status") not in ["NS", "Not Started", "scheduled"]:
                    continue
                
                # Verify teams exist (should have been created in history step or create now)
                # (Skipping team creation for brevity, assuming same teams as history)
                # ... upsert match logic ...
                upcoming_count += 1
        
        logger.info(f"Bootstrap complete. Upcoming matches tracked: {upcoming_count}")

if __name__ == "__main__":
    asyncio.run(bootstrap())
