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
                
                # Find matching match and determine closing price
                closing_prices = []
                pinnacle_price = None
                
                for event in raw_odds:
                    if event.get('id') == match.api_id:
                        for bm in event.get('bookmakers', []):
                            for mkt in bm.get('markets', []):
                                if mkt.get('key') == 'h2h':
                                    outcomes = {o['name']: o['price'] for o in mkt.get('outcomes', [])}
                                    
                                    # Map selection name
                                    target_name = bet.selection
                                    if bet.selection == "Home" and match.home_team:
                                        target_name = match.home_team.name
                                    elif bet.selection == "Away" and match.away_team:
                                        target_name = match.away_team.name
                                    elif bet.selection == "Draw":
                                        target_name = "Draw"
                                        
                                    # Find the price for our selection
                                    price = outcomes.get(target_name)
                                    if not price:
                                        # Fuzzy match fallback
                                        for name, p in outcomes.items():
                                            if target_name.lower() in name.lower() or name.lower() in target_name.lower():
                                                price = p
                                                break
                                    
                                    if price:
                                        closing_prices.append(price)
                                        if bm.get('key') == 'pinnacle':
                                            pinnacle_price = price

                # Logic: Pinnacle first (sharpest), then market average
                final_closing = pinnacle_price
                if not final_closing and closing_prices:
                    final_closing = sum(closing_prices) / len(closing_prices)
                    logger.debug(f"Pinnacle missing for Bet {bet.id}; using market average ({len(closing_prices)} bookies)")
                
                if final_closing:
                    bet.closing_odds = round(final_closing, 3)
                    # CLV = (Opening Odds / Closing Odds) - 1
                    bet.clv = round((bet.decimal_odds / final_closing) - 1, 4)
                    logger.info(f"CLV recorded for Bet {bet.id}: {bet.clv:+.2%}")
                else:
                    logger.warning(f"Could not find closing odds for Bet {bet.id}")

                
            except Exception as e:
                logger.error(f"Error fetching closing odds for Match {match.id}: {e}")
        
        await db.commit()
