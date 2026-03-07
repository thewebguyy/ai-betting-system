"""
scrapers/data_fetch.py
Wrapper functions for free sports data APIs.
Sources:
  - API-Football (RapidAPI free plan)  — stats, fixtures, injuries
  - The Odds API (500 req/mo free)     — cross-book odds
  - TheSportsDB (key=2 free)           — general data
  - BallDontLie (NBA, no key)          — NBA stats
  - football-data.org (free tier)      — historical results
"""

import time
from typing import Optional
import requests
from tenacity import retry, stop_after_attempt, wait_exponential
from loguru import logger
from fake_useragent import UserAgent

from backend.config import get_settings

settings = get_settings()
ua = UserAgent()

# ── Rate-limit state ──────────────────────────────────────────────────────────
_api_football_calls: list[float] = []
_odds_api_calls: list[float] = []

BASE_HEADERS_RAPIDAPI = {
    "X-RapidAPI-Key": settings.api_football_key,
    "X-RapidAPI-Host": "v3.football.api-sports.io",
    "User-Agent": ua.random,
}

FOOTBALL_DATA_BASE = "https://api.football-data.org/v4"
SPORTSDB_BASE = "https://www.thesportsdb.com/api/v1/json"
ODDS_API_BASE = "https://api.the-odds-api.com/v4"
API_FOOTBALL_BASE = "https://v3.football.api-sports.io"


def _check_rate(calls_list: list[float], limit: int, window: int = 3600) -> bool:
    """Return True if we are under rate limit."""
    now = time.time()
    calls_list[:] = [t for t in calls_list if now - t < window]
    if len(calls_list) >= limit:
        logger.warning("Rate limit reached, skipping call.")
        return False
    calls_list.append(now)
    return True


# ─── API-Football ─────────────────────────────────────────────────────────────
@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def fetch_fixtures(league_id: int = 39, season: int = 2024) -> list[dict]:
    """Fetch upcoming fixtures from API-Football (free: 100 req/day)."""
    if not settings.api_football_key:
        logger.warning("API_FOOTBALL_KEY not set — returning empty fixtures.")
        return []
    if not _check_rate(_api_football_calls, 95, 86400):
        return []

    url = f"{API_FOOTBALL_BASE}/fixtures"
    params = {"league": league_id, "season": season, "status": "NS"}
    resp = requests.get(url, headers=BASE_HEADERS_RAPIDAPI, params=params, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    return data.get("response", [])


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def fetch_team_statistics(team_id: int, league_id: int, season: int = 2024) -> dict:
    if not settings.api_football_key:
        return {}
    if not _check_rate(_api_football_calls, 95, 86400):
        return {}

    url = f"{API_FOOTBALL_BASE}/teams/statistics"
    params = {"team": team_id, "league": league_id, "season": season}
    resp = requests.get(url, headers=BASE_HEADERS_RAPIDAPI, params=params, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    return data.get("response", {})


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def fetch_injuries(fixture_id: int) -> list[dict]:
    if not settings.api_football_key:
        return []
    if not _check_rate(_api_football_calls, 95, 86400):
        return []

    url = f"{API_FOOTBALL_BASE}/injuries"
    params = {"fixture": fixture_id}
    resp = requests.get(url, headers=BASE_HEADERS_RAPIDAPI, params=params, timeout=15)
    resp.raise_for_status()
    return resp.json().get("response", [])


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def fetch_head_to_head(home_id: int, away_id: int, last: int = 10) -> list[dict]:
    if not settings.api_football_key:
        return []
    if not _check_rate(_api_football_calls, 95, 86400):
        return []

    url = f"{API_FOOTBALL_BASE}/fixtures/headtohead"
    params = {"h2h": f"{home_id}-{away_id}", "last": last}
    resp = requests.get(url, headers=BASE_HEADERS_RAPIDAPI, params=params, timeout=15)
    resp.raise_for_status()
    return resp.json().get("response", [])


# ─── The Odds API ─────────────────────────────────────────────────────────────
@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def fetch_odds_api(sport: str = "soccer_epl", regions: str = "uk,eu,us", markets: str = "h2h") -> list[dict]:
    """Fetch odds from multiple bookmakers via The Odds API (500 req/mo free)."""
    if not settings.odds_api_key:
        logger.warning("ODDS_API_KEY not set — returning empty odds.")
        return []
    if not _check_rate(_odds_api_calls, 470, 2592000):  # ~500/month
        return []

    url = f"{ODDS_API_BASE}/sports/{sport}/odds"
    params = {
        "apiKey": settings.odds_api_key,
        "regions": regions,
        "markets": markets,
        "oddsFormat": "decimal",
        "dateFormat": "iso",
    }
    resp = requests.get(url, params=params, timeout=15)
    resp.raise_for_status()
    remaining = resp.headers.get("x-requests-remaining", "?")
    logger.info(f"Odds API requests remaining: {remaining}")
    return resp.json()


# ─── TheSportsDB ──────────────────────────────────────────────────────────────
def fetch_sportsdb_events(league_id: str = "4328", season: str = "2024-2025") -> list[dict]:
    """Free public endpoint — key=2."""
    url = f"{SPORTSDB_BASE}/{settings.thesportsdb_api_key}/eventsseason.php"
    params = {"id": league_id, "s": season}
    try:
        resp = requests.get(url, params=params, timeout=15)
        resp.raise_for_status()
        return resp.json().get("events") or []
    except Exception as e:
        logger.error(f"TheSportsDB error: {e}")
        return []


# ─── football-data.org ────────────────────────────────────────────────────────
def fetch_football_data_matches(competition: str = "PL", season: Optional[str] = None) -> list[dict]:
    """Free plan: 10 competitions, last 10 seasons."""
    url = f"{FOOTBALL_DATA_BASE}/competitions/{competition}/matches"
    params = {}
    if season:
        params["season"] = season
    headers = {"X-Auth-Token": ""}  # Free tier — no token needed for historical
    try:
        resp = requests.get(url, headers=headers, params=params, timeout=15)
        resp.raise_for_status()
        return resp.json().get("matches", [])
    except Exception as e:
        logger.error(f"football-data.org error: {e}")
        return []


# ─── Data normaliser ──────────────────────────────────────────────────────────
def normalise_fixture(raw: dict, source: str = "api_football") -> dict:
    """Standardise fixture data to our internal schema."""
    if source == "api_football":
        fix = raw.get("fixture", {})
        teams = raw.get("teams", {})
        return {
            "api_id": str(fix.get("id", "")),
            "match_date": fix.get("date", ""),
            "status": fix.get("status", {}).get("short", "NS"),
            "venue": fix.get("venue", {}).get("name", ""),
            "home_team": teams.get("home", {}).get("name", ""),
            "away_team": teams.get("away", {}).get("name", ""),
            "home_team_api_id": str(teams.get("home", {}).get("id", "")),
            "away_team_api_id": str(teams.get("away", {}).get("id", "")),
            "league_id": str(raw.get("league", {}).get("id", "")),
            "season": str(raw.get("league", {}).get("season", "")),
        }
    return raw
