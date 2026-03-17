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
from scrapers.data_fetch import fetch_odds_api
from sqlalchemy import select

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
    "football": "https://www.sportybet.com/ke/sport/football",
}


async def scrape_from_odds_api(sport: str = "soccer_epl") -> list[dict]:
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

            await page.goto(url, wait_until="networkidle", timeout=30000)
            await asyncio.sleep(2)

            # generic extraction for SportyBet's current layout
            try:
                # SportyBet often uses .m-table-row or .m-event-item
                matches = await page.query_selector_all(".m-table-row, .m-event-item")
                if not matches:
                     matches = await page.query_selector_all("div[class*='event-item']")

                for m in matches[:20]:
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
                    except Exception:
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


def convert_american_to_decimal(american: int) -> float:
    """Convert American odds to decimal format."""
    if american > 0:
        return round(american / 100 + 1, 4)
    else:
        return round(100 / abs(american) + 1, 4)


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

    # Fallback: SportyBet (no API needed)
    try:
        sb_events = await scrape_sportybet_playwright()
        results["sportybet"] = len(sb_events)
    except Exception as e:
        logger.error(f"SportyBet scrape failed: {e}")

    logger.info(f"Scrape complete: {results}")
    return results
