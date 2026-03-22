"""
tests/smoke_test_pipeline.py
A validation script to prove the 'connected plumbing' actually works.
This script mocks the external APIs and runs the daily scan logic, 
then verifies the database contains correctly linked data.
"""

import asyncio
import sys
import os

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from unittest.mock import patch, AsyncMock
from datetime import datetime, timedelta

from automation.workflows import job_daily_scan
from backend.database import AsyncSessionLocal, Base, engine
from backend.models import Match, Team, OddsHistory

async def setup_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

async def run_smoke_test():
    await setup_db()
    
    print("\n[Smoke Test] Initializing Mocks...")
    
    # 1. Mock API-Football Fixtures (Primary Source)
    # Using 'Manchester United' as the canonical name in the DB
    mock_fixtures = [
        {
            "fixture": {"id": 1001, "date": (datetime.utcnow() + timedelta(days=1)).isoformat(), "status": {"short": "NS"}, "venue": {"name": "Old Trafford"}},
            "league": {"id": 39, "season": 2024},
            "teams": {
                "home": {"id": 33, "name": "Manchester United"},
                "away": {"id": 34, "name": "Newcastle"}
            }
        }
    ]
    
    # 2. Mock Scraped Odds (Secondary Source - SportyBet)
    # Using 'Man Utd' to test the robust matching logic (is_same_team)
    mock_scraped_odds = [
        {
            "bookmaker": "sportybet",
            "home_team": "Man Utd", 
            "away_team": "Newcastle United",
            "home_odds": 2.10,
            "draw_odds": 3.50,
            "away_odds": 3.20
        }
    ]

    # Patching all external dependencies
    with patch("scrapers.data_fetch.fetch_fixtures", AsyncMock(return_value=mock_fixtures)), \
         patch("scrapers.odds_scraper.scrape_all_bookmakers", AsyncMock(side_effect=lambda: None)), \
         patch("scrapers.odds_scraper.scrape_sportybet_playwright", AsyncMock(return_value=mock_scraped_odds)), \
         patch("scrapers.odds_api.scrape_from_odds_api", AsyncMock(return_value=[])), \
         patch("automation.xg_processor.process_all_leagues_xg", AsyncMock(return_value=None)), \
         patch("models.value_model.detect_value_bets_for_upcoming", AsyncMock(return_value=0)):
         
        print("[Smoke Test] Running job_daily_scan...")
        # Manually run parts of the job to verify the internal logic
        await job_daily_scan()
        
        # We also need to manually trigger persist_scraping_results because we mocked scrape_all_bookmakers
        from scrapers.odds_scraper import persist_scraping_results
        async with AsyncSessionLocal() as db:
            await persist_scraping_results(db, mock_scraped_odds)
            await db.commit()
        
    # 3. VERIFICATION
    async with AsyncSessionLocal() as db:
        from sqlalchemy import select
        
        # Check Teams
        teams = (await db.execute(select(Team))).scalars().all()
        print(f"[Verification] Teams in DB: {[t.name for t in teams]}")
        
        # Check Match linking
        matches = (await db.execute(select(Match))).scalars().all()
        assert len(matches) == 1
        m = matches[0]
        print(f"[Verification] Match created: ID {m.id}, Home Team ID {m.home_team_id}")
        
        # Check Odds persistence with fuzzy matching
        odds = (await db.execute(select(OddsHistory))).scalars().all()
        print(f"[Verification] Odds records found: {len(odds)}")
        
        if len(odds) == 1 and odds[0].match_id == m.id:
            print("\n✅ SMOKE TEST PASSED: 'Man Utd' was correctly linked to 'Manchester United'!")
        else:
            print("\n❌ SMOKE TEST FAILED: Odds were not correctly linked to the Match.")
            if len(odds) > 0:
                print(f"   Odds Match ID: {odds[0].match_id}, Actual Match ID: {m.id}")

if __name__ == "__main__":
    asyncio.run(run_smoke_test())
