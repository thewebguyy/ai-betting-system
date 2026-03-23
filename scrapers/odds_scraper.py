"""
scrapers/odds_scraper.py
Async multi-bookmaker odds scraper.
  - Primary:  The Odds API (rate-limited free tier)
  - Fallback: Playwright headless scrape for SportyBet
Stores time-series in DB for line-movement tracking.
"""

import asyncio
import json
from datetime import datetime
from typing import Optional

from loguru import logger
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout
from fake_useragent import UserAgent

from backend.config import get_settings
from backend.database import AsyncSessionLocal
from backend.models import OddsHistory, Match
from backend.utils import is_same_team, jittered_sleep, jittered_goto
from sqlalchemy import select
from sqlalchemy.orm import joinedload

settings = get_settings()
ua = UserAgent()

# Bookmakers available via The Odds API
BOOKMAKER_MAP = {
    "bet365": "bet365",
    "pinnacle": "pinnacle",
    "draftkings": "draftkings",
    "betway": "betway",
    "william_hill": "williamhill",
    "unibet": "unibet",
}

SPORTYBET_SPORT_URLS = {
    "football": "https://www.sportybet.com/ng/sport/football",
}

GENERIC_BOOKMAKER_URLS = {
    "betway": "https://www.betway.com.gh/sport/soccer",
    "1xbet": "https://1xbet.com/en/line/football",
    "melbet": "https://melbet.com/en/line/football",
}



async def scrape_from_odds_api(sport: str = "soccer_epl") -> list[str]:
    """
    Fetch and store odds (supports The Odds API and SportAPI).
    """
    from scrapers.data_fetch import get_active_source
    raw = await fetch_odds_api(sport=sport, regions="uk,eu", markets="h2h,totals")
    if not raw:
        return []

    source = get_active_source()
    stored = []
    async with AsyncSessionLocal() as db:
        if source == "sportapi7":
            # Parsing SportAPI specific structure
            for event_odds in raw:
                fid = str(event_odds.get("fid", ""))
                # Find matching match in our DB
                result = await db.execute(select(Match).where(Match.api_id == fid))
                match = result.scalar_one_or_none()
                if not match: continue

                choices = {c["name"]: c.get("fractionalValue") for c in event_odds.get("choices", [])}
                
                # Conversion helper for fractional (SportAPI uses strings like "2/1")
                def parse_frac(v):
                    if not v or "/" not in v: return None
                    try:
                        n, d = map(int, v.split("/"))
                        return round(n/d + 1, 3)
                    except: return None

                record = OddsHistory(
                    match_id=match.id,
                    bookmaker="sportapi7",
                    market="1X2",
                    home_odds=parse_frac(choices.get("1")),
                    draw_odds=parse_frac(choices.get("X")),
                    away_odds=parse_frac(choices.get("2")),
                    fetched_at=datetime.utcnow(),
                )
                db.add(record)
                stored.append("sportapi7")
        else:
            # Parsing Standard The Odds API structure
            for event in raw:
                match_api_id = event.get("id", "")
                result = await db.execute(select(Match).where(Match.api_id == match_api_id))
                match = result.scalar_one_or_none()
                match_id = match.id if match else None

                for bm in event.get("bookmakers", []):
                    bm_key = bm.get("key", "")
                    for market in bm.get("markets", []):
                        market_key = market.get("key", "")
                        outcomes = {o["name"]: o["price"] for o in market.get("outcomes", [])}
                        home_name = event.get("home_team", "")
                        away_name = event.get("away_team", "")

                        record = OddsHistory(
                            match_id=match_id,
                            bookmaker=bm_key,
                            market="1X2" if market_key == "h2h" else market_key.upper(),
                            home_odds=outcomes.get(home_name),
                            away_odds=outcomes.get(away_name),
                            draw_odds=outcomes.get("Draw"),
                            over_odds=outcomes.get("Over 2.5"),
                            under_odds=outcomes.get("Under 2.5"),
                            fetched_at=datetime.utcnow(),
                        )
                        db.add(record)
                        stored.append(bm_key)

        await db.commit()
        logger.info(f"Stored {len(stored)} odds records.")
    return stored


async def scrape_sportybet_playwright(sport: str = "football") -> list[dict]:
    """
    Playwright headless scraper for SportyBet (fallback / additional source).
    NOTE: SportyBet's DOM changes frequently; update selectors as needed.
    
    WARNING (Architecture): Jittered sleep and stealth plugins are stop-gap measures. 
    Modern anti-scraping systems use browser fingerprinting and behavioral analysis.
    This component is inherently brittle and risky for production.
    TODO: The robust fix is migrating entirely to official API tiers (e.g. The Odds API).
    
    Returns list of raw match dicts.
    """
    url = SPORTYBET_SPORT_URLS.get(sport, SPORTYBET_SPORT_URLS["football"])
    events = []

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-blink-features=AutomationControlled",
                ]
            )
            context = await browser.new_context(
                user_agent=ua.random,
                viewport={"width": 1280, "height": 800},
                locale="en-GB",
            )
            page = await context.new_page()

            # Anti-detection: hide navigator.webdriver
            await page.add_init_script(
                "Object.defineProperty(navigator,'webdriver',{get:()=>undefined})"
            )

            await jittered_goto(page, url)

            # generic extraction for SportyBet's current layout
            try:
                # SportyBet often uses .m-table-row or .m-event-item
                found_matches = await page.query_selector_all(".m-table-row, .m-event-item")
                if not found_matches:
                     found_matches = await page.query_selector_all("div[class*='event-item']")

                for m in found_matches[:20]:
                    try:
                        # Improved selectors for teams and odds
                        teams_el = await m.query_selector_all(".m-team-name, .team-name")
                        odds_el = await m.query_selector_all(".m-outcome-value, .m-odd-value")

                        if not teams_el:
                            teams_el = await m.query_selector_all("div[class*='team-name']")
                        
                        home = (await teams_el[0].inner_text()) if len(teams_el) > 0 else ""
                        away = (await teams_el[1].inner_text()) if len(teams_el) > 1 else ""

                        # Odds are usually presented as Home, Draw, Away in 1X2 market
                        home_odds = float((await odds_el[0].inner_text()).strip()) if len(odds_el) > 0 else None
                        draw_odds = float((await odds_el[1].inner_text()).strip()) if len(odds_el) > 1 else None
                        away_odds = float((await odds_el[2].inner_text()).strip()) if len(odds_el) > 2 else None


                        events.append({
                            "bookmaker": "sportybet",
                            "home_team": home.strip(),
                            "away_team": away.strip(),
                            "home_odds": home_odds,
                            "draw_odds": draw_odds,
                            "away_odds": away_odds,
                        })
                    except (ValueError, IndexError, AttributeError) as e:
                        logger.debug(f"Row skip: {e}")
                        continue
            except Exception as e:
                logger.warning(f"SportyBet selector error: {e}")

            await browser.close()

    except PlaywrightTimeout as e:
        logger.error(f"Playwright timeout scraping SportyBet: {e}")
    except Exception as e:
        logger.error(f"Playwright error: {e}")

    logger.info(f"SportyBet scraper found {len(events)} events.")
    return events


async def scrape_bet9ja_xhr() -> list[dict]:
    """
    Direct XHR extraction for Bet9ja.
    Uses httpx to fetch JSON from the internal API.
    """
    import httpx
    # Simplified endpoint from the brief
    url = "https://sports.bet9ja.com/desktop/feapi/PalimpsestAjax/GetOdds"
    params = {
        "pParam": "1", # generic param for soccer/popular
        "is_cocktail": "0"
    }
    headers = {
        "User-Agent": ua.random,
        "Accept": "application/json",
        "Origin": "https://sports.bet9ja.com",
        "Referer": "https://sports.bet9ja.com/desktop/sport/soccer",
    }
    
    events = []
    try:
        async with httpx.AsyncClient(headers=headers, timeout=10.0) as client:
            resp = await client.get(url, params=params)
            if resp.status_code == 200:
                data = resp.json()
                # Bet9ja response structure parsing (example logic)
                # Usually nested under 'DS' or 'data'
                matches = data.get("data", {}).get("groupEvents", [])
                for ge in matches:
                    for event in ge.get("events", []):
                        try:
                            # Extract 1X2 odds
                            odds_list = event.get("odds", [])
                            h_odds = next((o["price"] for o in odds_list if o["name"] == "1"), None)
                            d_odds = next((o["price"] for o in odds_list if o["name"] == "X"), None)
                            a_odds = next((o["price"] for o in odds_list if o["name"] == "2"), None)
                            
                            events.append({
                                "bookmaker": "bet9ja",
                                "home_team": event.get("event_name", "").split(" - ")[0],
                                "away_team": event.get("event_name", "").split(" - ")[1] if " - " in event.get("event_name", "") else "",
                                "home_odds": float(h_odds) if h_odds else None,
                                "draw_odds": float(d_odds) if d_odds else None,
                                "away_odds": float(a_odds) if a_odds else None,
                            })
                        except (KeyError, ValueError, IndexError, TypeError):
                            continue
    except Exception as e:
        logger.error(f"Bet9ja XHR scrape failed: {e}")
        
    return events


async def scrape_generic_playwright(bookmaker: str) -> list[dict]:
    """
    Generic Playwright scraper for 1xBet, Melbet, etc.
    WARNING: Like the SportyBet scraper, this is brittle and subject to IP bans 
    despite randomized delays. Move to paid API feeds as soon as budget permits.
    """
    url = GENERIC_BOOKMAKER_URLS.get(bookmaker)
    if not url: return []
    events = []

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page(user_agent=ua.random)
            await page.add_init_script("Object.defineProperty(navigator,'webdriver',{get:()=>undefined})")
            
            await jittered_goto(page, url)

            # 1xBet/Melbet structure (complex, using generic selectors)
            # This is a representative sample; real implementation would be more robust
            found_matches = await page.query_selector_all(".bet-item, .event-item")
            for m in found_matches[:15]:
                try:
                    teams = await m.query_selector_all(".team-name, .c-events__team")
                    home = await teams[0].inner_text() if len(teams) > 0 else ""
                    away = await teams[1].inner_text() if len(teams) > 1 else ""
                    
                    odds = await m.query_selector_all(".odds-value, .c-bets__inner")
                    h_odds = float((await odds[0].inner_text()).strip()) if len(odds) > 0 else None
                    a_odds = float((await odds[2].inner_text()).strip()) if len(odds) > 2 else None
                    
                    events.append({
                        "bookmaker": bookmaker,
                        "home_team": home.strip(),
                        "away_team": away.strip(),
                        "home_odds": h_odds,
                        "away_odds": a_odds,
                    })
                except: continue
            await browser.close()
    except Exception as e:
        logger.error(f"Scrape error for {bookmaker}: {e}")
    
    return events



def convert_american_to_decimal(american: int) -> float:
    """Convert American odds to decimal format."""
    if american > 0:
        return round(american / 100 + 1, 4)
    else:
        return round(100 / abs(american) + 1, 4)


async def persist_scraping_results(db, events: list[dict]) -> int:
    """
    Match manual scraping results (team names) to Match IDs and persist.
    """
    from sqlalchemy import or_, and_
    from datetime import timedelta
    
    stored_count = 0
    now = datetime.utcnow()
    
    # 1. Get all scheduled matches in the next 3 days
    stmt = select(Match).options(joinedload(Match.home_team), joinedload(Match.away_team)).where(
        Match.status == "scheduled",
        Match.match_date >= now - timedelta(hours=6),
        Match.match_date <= now + timedelta(days=3)
    )
    result = await db.execute(stmt)
    upcoming_matches = result.scalars().all()
    
    for event in events:
        home_name = event.get("home_team", "").lower()
        away_name = event.get("away_team", "").lower()
        
        # 2. Improved name matching
        matched_match = None
        for m in upcoming_matches:
            m_home = m.home_team.name if m.home_team else ""
            m_away = m.away_team.name if m.away_team else ""
            
            # Use utility for more robust matching
            if is_same_team(home_name, m_home) and is_same_team(away_name, m_away):
                matched_match = m
                break
        
        if matched_match:
            mid = matched_match.id
            record = OddsHistory(
                match_id=mid,
                bookmaker=event["bookmaker"],
                market="1X2",
                home_odds=event.get("home_odds"),
                draw_odds=event.get("draw_odds"),
                away_odds=event.get("away_odds"),
                fetched_at=datetime.utcnow(),
            )
            stored_count += 1
        else:
            logger.debug(f"Failed to match fixture: {home_name} vs {away_name} for {event['bookmaker']}")
            
    # 3. Data Quality Monitoring
    if events:
        match_rate = stored_count / len(events)
        if match_rate < 0.40:
             logger.error(f"CRITICAL DATA QUALITY ISSUE: Match rate for {events[0]['bookmaker']} is only {match_rate:.1%}. Scrapers may need update!")
             # Optional: Trigger notification
        else:
             logger.info(f"Odds mapped: {stored_count}/{len(events)} ({match_rate:.1%}) for {events[0]['bookmaker']}")

    await db.commit()
    return stored_count


def convert_fractional_to_decimal(num: int, den: int) -> float:
    """Convert fractional odds (e.g. 5/2) to decimal."""
    return round(num / den + 1, 4)


async def scrape_all_bookmakers(sport: str = "soccer_epl") -> dict:
    """Orchestrate all scrapers and return summary."""
    results = {"odds_api": 0, "sportybet": 0}

    # Primary: The Odds API
    try:
        stored = await scrape_from_odds_api(sport=sport)
        results["odds_api"] = len(stored)
    except Exception as e:
        logger.error(f"Odds API scrape failed: {e}")

    # Playwright & XHR sources
    async with AsyncSessionLocal() as db:
        for bm in ["sportybet", "bet9ja", "betway", "1xbet", "melbet"]:
            try:
                bm_events = []
                if bm == "sportybet":
                    bm_events = await scrape_sportybet_playwright()
                elif bm == "bet9ja":
                    bm_events = await scrape_bet9ja_xhr()
                else:
                    bm_events = await scrape_generic_playwright(bm)
                
                if bm_events:
                    stored_count = await persist_scraping_results(db, bm_events)
                    results[bm] = stored_count
                    logger.debug(f"Persisted {stored_count} odds for {bm}")
                else:
                    results[bm] = 0
            except Exception as e:
                logger.error(f"{bm} scrape failed: {e}")

    logger.info(f"Scrape complete: {results}")
    return results

