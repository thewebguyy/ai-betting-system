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
    Fetch and store odds from The Odds API for all matches.
    Returns list of stored records.
    """
    raw = fetch_odds_api(sport=sport, regions="uk,eu", markets="h2h,totals")
    if not raw:
        return []

    stored = []
    async with AsyncSessionLocal() as db:
        for event in raw:
            # Find or skip match (we match on api_id from fixture data)
            match_api_id = event.get("id", "")
            result = await db.execute(
                select(Match).where(Match.api_id == match_api_id)
            )
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
        logger.info(f"Stored {len(stored)} odds records from The Odds API.")
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

            # Generic extraction — adjust selectors based on current site structure
            # SportyBet uses class-based selectors; these are representative
            try:
                matches = await page.query_selector_all(".m-eventItem")
                for m in matches[:20]:  # cap at 20 to be polite
                    try:
                        teams_el = await m.query_selector_all(".m-teamName")
                        odds_el = await m.query_selector_all(".m-odd")

                        home = (await teams_el[0].inner_text()) if len(teams_el) > 0 else ""
                        away = (await teams_el[1].inner_text()) if len(teams_el) > 1 else ""

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
