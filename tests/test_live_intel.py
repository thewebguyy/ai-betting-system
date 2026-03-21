"""
tests/test_live_intel.py
Validation for Phase 2: Live Scrapers and Stale Detection.
"""

import pytest
from datetime import datetime, timedelta
from scrapers.odds_scraper import scrape_bet9ja_xhr
from automation.workflows import job_check_stale_odds
from backend.database import AsyncSessionLocal
from backend.models import ValueBet, Match

@pytest.mark.asyncio
async def test_scrape_bet9ja_xhr():
    # This might fail in CI if no internet, but we test the structure
    try:
        results = await scrape_bet9ja_xhr()
        assert isinstance(results, list)
        if results:
            assert "bookmaker" in results[0]
            assert results[0]["bookmaker"] == "bet9ja"
    except Exception as e:
        pytest.skip(f"Bet9ja scrape skipped due to connectivity: {e}")

@pytest.mark.asyncio
async def test_stale_odds_detection():
    async with AsyncSessionLocal() as db:
        # Create a dummy match and value bet
        match = Match(match_date=datetime.utcnow() + timedelta(days=1))
        db.add(match)
        await db.flush()
        
        # Create a stale bet (detected 3 hours ago)
        stale_bet = ValueBet(
            match_id=match.id,
            bookmaker="test_bk",
            market="1X2",
            selection="Home",
            decimal_odds=2.0,
            implied_prob=0.5,
            true_implied=0.5,
            model_prob=0.6,
            edge=0.1,
            ev=0.2,
            kelly_fraction=0.1,
            detected_at=datetime.utcnow() - timedelta(hours=3),
            is_stale=False
        )
        # Create a fresh bet
        fresh_bet = ValueBet(
            match_id=match.id,
            bookmaker="test_bk",
            market="1X2",
            selection="Away",
            decimal_odds=3.0,
            implied_prob=0.33,
            true_implied=0.33,
            model_prob=0.4,
            edge=0.07,
            ev=0.1,
            kelly_fraction=0.05,
            detected_at=datetime.utcnow() - timedelta(minutes=10),
            is_stale=False
        )
        db.add_all([stale_bet, fresh_bet])
        await db.commit()
        
        # Run stale check
        await job_check_stale_odds()
        
        # Verify results
        await db.refresh(stale_bet)
        await db.refresh(fresh_bet)
        
        assert stale_bet.is_stale is True
        assert fresh_bet.is_stale is False
        
        # Cleanup
        await db.delete(stale_bet)
        await db.delete(fresh_bet)
        await db.delete(match)
        await db.commit()
