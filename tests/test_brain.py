"""
tests/test_brain.py
Validation for Phase 3: Intelligence Scoring and Recommendations.
"""

import pytest
from datetime import datetime, timedelta
from models.value_model import calculate_intelligence_score
from automation.workflows import job_generate_recommendations
from backend.database import AsyncSessionLocal
from backend.models import ValueBet, Match, Recommendation

def test_intelligence_scoring_logic():
    # Test high EV, high confidence
    score_high = calculate_intelligence_score(ev=0.2, confidence=0.8, overround=0.05, risks_found=False)
    assert score_high > 0.7
    
    # Test low score due to risk
    score_risk = calculate_intelligence_score(ev=0.2, confidence=0.8, overround=0.05, risks_found=True)
    assert score_risk < score_high
    
    # Test low score due to high vig
    score_vig = calculate_intelligence_score(ev=0.1, confidence=0.5, overround=0.20, risks_found=False)
    assert score_vig < 0.5

@pytest.mark.asyncio
async def test_recommendation_generation():
    async with AsyncSessionLocal() as db:
        # Create dummy match and value bet
        match = Match(match_date=datetime.utcnow() + timedelta(days=1))
        db.add(match)
        await db.flush()
        
        # Sniper candidate
        sniper_bet = ValueBet(
            match_id=match.id,
            bookmaker="test_bk",
            market="1X2",
            selection="Home",
            decimal_odds=2.5,
            implied_prob=0.4,
            true_implied=0.4,
            model_prob=0.6,
            edge=0.2,
            ev=0.5,
            kelly_fraction=0.1,
            intelligence_score=0.9,
            status="pending"
        )
        
        # Avoid candidate
        avoid_bet = ValueBet(
            match_id=match.id,
            bookmaker="test_bk",
            market="1X2",
            selection="Away",
            decimal_odds=3.0,
            implied_prob=0.33,
            true_implied=0.33,
            model_prob=0.35,
            edge=0.02,
            ev=0.05,
            kelly_fraction=0.01,
            intelligence_score=0.25,
            status="pending"
        )
        
        db.add_all([sniper_bet, avoid_bet])
        await db.commit()
        
        # Run recommendation generation
        await job_generate_recommendations()
        
        # Verify
        stmt = select(Recommendation).where(Recommendation.match_id == match.id)
        recs = (await db.execute(stmt)).scalars().all()
        
        assert len(recs) >= 2
        
        sniper_rec = next(r for r in recs if r.value_bet_id == sniper_bet.id)
        avoid_rec = next(r for r in recs if r.value_bet_id == avoid_bet.id)
        
        assert sniper_rec.category == "Sniper"
        assert avoid_rec.category == "Avoid"
        
        # Cleanup
        for r in recs: await db.delete(r)
        await db.delete(sniper_bet)
        await db.delete(avoid_bet)
        await db.delete(match)
        await db.commit()
