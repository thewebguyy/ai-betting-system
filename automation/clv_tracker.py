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

                # LOGIC: Pinnacle is the gold standard for CLV because of minimal margin.
                # If we use a market average (including softer books), it's a methodological downgrade
                # that measures "did we beat recreational money", not true true probability edge.
                final_closing = pinnacle_price
                if not final_closing and closing_prices:
                    final_closing = sum(closing_prices) / len(closing_prices)
                    logger.warning(
                        f"METHODOLOGICAL DOWNGRADE: Pinnacle missing for Bet {bet.id}. "
                        f"Using market average of {len(closing_prices)} bookies for CLV calculation. "
                        f"This is a less informative signal."
                    )
                
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
    
    # NEW: Settle observations in JSONL
    await settle_jsonl_observations()

async def settle_jsonl_observations():
    """
    Read observations from JSONL, fetch closing odds, and update the file.
    """
    from backend.config import get_settings
    import json
    import os
    settings = get_settings()
    log_file = settings.clv_log_path
    
    if not os.path.exists(log_file):
        return
        
    updated_rows = []
    with open(log_file, "r") as f:
        for line in f:
            if not line.strip(): continue
            data = json.loads(line)
            
            # If closing_odds is null and match kickoff has passed
            kickoff = datetime.fromisoformat(data["kickoff_time"])
            if data.get("closing_odds") is None and datetime.utcnow() > kickoff:
                # Fetch closing odds for this match
                try:
                    # Attempt to find closing odds in db (OddsHistory) near kickoff
                    async with AsyncSessionLocal() as db:
                        stmt = (
                            select(OddsHistory)
                            .where(
                                OddsHistory.match_id == data["match_id"],
                                OddsHistory.fetched_at >= kickoff - timedelta(minutes=60),
                                OddsHistory.fetched_at <= kickoff + timedelta(minutes=15)
                            )
                            .order_by(OddsHistory.fetched_at.desc())
                        )
                        result = await db.execute(stmt)
                        odds_list = result.scalars().all()
                        
                        if odds_list:
                            pinnacle_odds = next((o for o in odds_list if o.bookmaker == "pinnacle"), None)
                            target_odds = pinnacle_odds if pinnacle_odds else odds_list[0]
                            
                            closing_val = None
                            selection = data["selection"]
                            if selection == "Home": closing_val = target_odds.home_odds
                            elif selection == "Draw": closing_val = target_odds.draw_odds
                            elif selection == "Away": closing_val = target_odds.away_odds
                            
                            if closing_val:
                                data["closing_odds"] = round(closing_val, 3)
                                data["closing_source"] = "pinnacle" if target_odds.bookmaker == "pinnacle" else "market_average"
                                data["CLV_delta_odds"] = round(closing_val - data["bookmaker_odds_at_prediction"], 3)
                                # CLV prob delta: implied_prob_model - implied_prob_market(closing)
                                # Actually the prompt says CLV_delta_prob = implied_prob_model - implied_prob_market
                                # But market implied at closing is 1/closing_odds
                                if closing_val > 0:
                                    data["CLV_delta_prob"] = round(data["implied_probability_model"] - (1/closing_val), 4)
                                    logger.info(f"Settled observation for {data['match_id']}: CLV={data['CLV_delta_odds']:+.3f}")
                except Exception as e:
                    logger.error(f"Error settling observation for {data['match_id']}: {e}")
            
            updated_rows.append(data)
            
    # Rewrite JSONL with updated rows
    with open(log_file, "w") as f:
        for row in updated_rows:
            f.write(json.dumps(row) + "\n")
