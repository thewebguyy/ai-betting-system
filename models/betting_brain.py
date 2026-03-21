"""
models/betting_brain.py
Orchestration layer for the AI Betting Intelligence System.
Aggregates model outputs into structured daily intelligence.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Dict, Any
from loguru import logger
from backend.cache import cache_set, cache_get
from backend.database import AsyncSessionLocal
from backend.models import ValueBet, Recommendation, Match
from sqlalchemy import select

@dataclass
class ScoredBet:
    selection: str
    bookmaker: str
    decimal_odds: float
    uds_score: float
    suggested_stake: float
    market: str
    ev: float

@dataclass
class DailyRecommendation:
    safe_bets: List[ScoredBet] = field(default_factory=list)
    sniper_bets: List[ScoredBet] = field(default_factory=list)
    aggressive_bets: List[ScoredBet] = field(default_factory=list)
    avoid_list: List[ScoredBet] = field(default_factory=list)
    claude_brief: str = ""
    total_bets_analyzed: int = 0
    bankroll: float = 1000.0
    generated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

class BettingBrain:
    """The central 'Brain' that assembles final recommendations."""
    
    @staticmethod
    async def get_latest_intelligence() -> Optional[Dict[str, Any]]:
        """Fetch the latest brain state from Redis."""
        return await cache_get("brain:daily:latest")

    @staticmethod
    async def refresh_daily_cache():
        """
        Aggregate Recommendations from DB and push to Redis.
        Triggered after match scan and recommendation generation.
        """
        logger.info("[BettingBrain] Refreshing daily intelligence cache…")
        try:
            async with AsyncSessionLocal() as db:
                # 1. Fetch recommendations for upcoming matches
                now = datetime.utcnow()
                stmt = select(Recommendation).join(ValueBet).join(Match).where(
                    Match.match_date > now,
                    Recommendation.created_at >= now.replace(hour=0, minute=0, second=0, microsecond=0)
                )
                result = await db.execute(stmt)
                recs = result.scalars().all()
                
                brain_data = DailyRecommendation(
                    total_bets_analyzed=len(recs)
                )
                
                for r in recs:
                    sb = ScoredBet(
                        selection=r.value_bet.selection,
                        bookmaker=r.value_bet.bookmaker,
                        decimal_odds=r.value_bet.decimal_odds,
                        uds_score=r.score * 100, # Normalize to 100
                        suggested_stake=r.value_bet.suggested_stake or 0.0,
                        market=r.value_bet.market,
                        ev=r.value_bet.ev
                    )
                    
                    # Dict-ify for JSON serialization
                    bet_dict = {
                        "selection": sb.selection,
                        "bookmaker": sb.bookmaker,
                        "decimal_odds": sb.decimal_odds,
                        "uds_score": sb.uds_score,
                        "suggested_stake": sb.suggested_stake,
                        "market": sb.market,
                        "ev": sb.ev
                    }
                    
                    if r.category == "Safe": brain_data.safe_bets.append(bet_dict)
                    elif r.category == "Sniper": brain_data.sniper_bets.append(bet_dict)
                    elif r.category == "Aggressive": brain_data.aggressive_bets.append(bet_dict)
                    elif r.category == "Avoid": brain_data.avoid_list.append(bet_dict)
                
                # 2. Get AI Brief (optional, could call Claude here)
                from models.ai_layer import call_claude
                brief_prompt = f"Summarise today's betting opportunities. Total analyzed: {len(recs)}. Top categories: Safe ({len(brain_data.safe_bets)}), Sniper ({len(brain_data.sniper_bets)}). Keep it to 3 sentences."
                brain_data.claude_brief = await call_claude(brief_prompt)
                
                # 3. Store in Redis
                final_json = {
                    "safe_bets": brain_data.safe_bets,
                    "sniper_bets": brain_data.sniper_bets,
                    "aggressive_bets": brain_data.aggressive_bets,
                    "avoid_list": brain_data.avoid_list,
                    "claude_brief": brain_data.claude_brief,
                    "total_bets_analyzed": brain_data.total_bets_analyzed,
                    "bankroll": brain_data.bankroll,
                    "generated_at": brain_data.generated_at
                }
                
                await cache_set("brain:daily:latest", final_json, ttl=86400) # 24h
                logger.info("[BettingBrain] Daily intelligence cache updated.")
                return final_json
        except Exception as e:
            logger.error(f"[BettingBrain] Cache refresh error: {e}")
            return None
