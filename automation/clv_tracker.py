"""
automation/clv_tracker.py
Tracks Closing Line Value (CLV) by fetching odds at kickoff.
"""

from loguru import logger
from sqlalchemy import select, update
from backend.database import AsyncSessionLocal
from backend.models import Match, Bet, OddsHistory
from scrapers.data_fetch import fetch_odds_api
from datetime import datetime, timedelta

async def track_closing_odds():
    """
    Find bets for matches that just started and fetch closing odds.
    """
    now = datetime.utcnow()
    # Matches that started between 5 and 15 minutes ago
    start_buffer = now - timedelta(minutes=15)
    end_buffer = now - timedelta(minutes=5)
    
    async with AsyncSessionLocal() as db:
        # Find bets where closing_odds is null and match started recently
        from sqlalchemy.orm import joinedload
        stmt = (
            select(Bet, Match)
            .join(Match, Bet.match_id == Match.id)
            .options(joinedload(Match.home_team), joinedload(Match.away_team))
            .where(
                Bet.closing_odds == None,
                Match.match_date >= start_buffer,
                Match.match_date <= end_buffer
            )
        )
        result = await db.execute(stmt)
        pending = result.all()
        
        if not pending:
            return
            
        logger.info(f"Tracking CLV for {len(pending)} bets…")
        
        for bet, match in pending:
            try:
                # Fetch closing odds (using Pinnacle as the gold standard for CLV)
                raw_odds = await fetch_odds_api(sport="soccer_epl", regions="uk,eu", markets="h2h")
                
                # Find matching match and bookmaker (Pinnacle)
                closing_price = None
                for event in raw_odds:
                    if event.get('id') == match.api_id:
                        for bm in event.get('bookmakers', []):
                            if bm.get('key') == 'pinnacle':
                                for mkt in bm.get('markets', []):
                                    if mkt.get('key') == 'h2h':
                                        outcomes = {o['name']: o['price'] for o in mkt.get('outcomes', [])}
                                        
                                        # Map selection name to actual team name
                                        target_name = bet.selection
                                        if bet.selection == "Home" and match.home_team:
                                            target_name = match.home_team.name
                                        elif bet.selection == "Away" and match.away_team:
                                            target_name = match.away_team.name
                                        elif bet.selection == "Draw":
                                            target_name = "Draw"
                                            
                                        # Some bookies use specific suffixes or prefixes; fuzzy match if exact fails
                                        closing_price = outcomes.get(target_name)
                                        if not closing_price:
                                            # Fuzzy fallback
                                            for name, price in outcomes.items():
                                                if target_name in name or name in target_name:
                                                    closing_price = price
                                                    break
                                        break
                
                if closing_price:
                    bet.closing_odds = closing_price
                    # CLV = (Opening Odds / Closing Odds) - 1
                    bet.clv = round((bet.decimal_odds / closing_price) - 1, 4)
                    logger.info(f"CLV recorded for Bet {bet.id}: {bet.clv:+.2%}")

                
            except Exception as e:
                logger.error(f"Error fetching closing odds for Match {match.id}: {e}")
        
        await db.commit()
