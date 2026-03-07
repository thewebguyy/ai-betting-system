"""
automation/workflows.py
APScheduler-based cron workflows.

Schedule:
  06:00  — Fetch fixtures + run value bet scan
  Every hour — Check odds discrepancies + line movement
  23:00  — Generate daily report + send summary alert
"""

import asyncio
from loguru import logger
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from pytz import utc


# ─── Job functions ────────────────────────────────────────────────────────────

async def job_daily_scan():
    """06:00 — Fetch new fixtures and run value bet model scan."""
    logger.info("[Scheduler] Running daily scan…")
    try:
        from scrapers.odds_scraper import scrape_all_bookmakers
        from scrapers.data_fetch import fetch_fixtures, normalise_fixture
        from models.value_model import detect_value_bets_for_upcoming
        from backend.database import AsyncSessionLocal
        from backend.models import Match, League, Team
        from sqlalchemy import select
        import json

        # Fetch and store upcoming fixtures
        raw_fixtures = fetch_fixtures(league_id=39, season=2024)
        async with AsyncSessionLocal() as db:
            for raw in raw_fixtures[:50]:
                norm = normalise_fixture(raw, "api_football")
                # Upsert match
                result = await db.execute(
                    select(Match).where(Match.api_id == norm["api_id"])
                )
                existing = result.scalar_one_or_none()
                if not existing:
                    match = Match(
                        api_id=norm["api_id"],
                        match_date=norm["match_date"],
                        status="scheduled",
                        venue=norm.get("venue", ""),
                    )
                    db.add(match)
            await db.commit()

        # Scrape odds
        await scrape_all_bookmakers()

        # Detect value bets
        count = await detect_value_bets_for_upcoming()
        logger.info(f"[Scheduler] Daily scan complete. Value bets found: {count}")
    except Exception as e:
        logger.error(f"[Scheduler] Daily scan error: {e}")


async def job_hourly_check():
    """Hourly — Check line movements and send alerts."""
    logger.info("[Scheduler] Running hourly line movement check…")
    try:
        from backend.database import AsyncSessionLocal
        from backend.models import Match, OddsHistory
        from backend.analytics import compute_line_movement
        from automation.notifications import send_telegram_message
        from sqlalchemy import select
        from datetime import datetime, timedelta

        now = datetime.utcnow()
        cutoff = now - timedelta(hours=48)

        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(Match).where(
                    Match.status == "scheduled",
                    Match.match_date >= now,
                    Match.match_date <= now + timedelta(days=2),
                )
            )
            upcoming = result.scalars().all()

            alerts_sent = 0
            for match in upcoming:
                movements = await compute_line_movement(db, match.id)
                if movements.get("alerts"):
                    msg = f"📉 Line Movement Alert — Match ID {match.id}\n"
                    for alert in movements["alerts"]:
                        msg += f"  {alert['field']}: {alert['from']} → {alert['to']} ({alert['delta_pct']:+.1f}%)\n"
                    await send_telegram_message(msg)
                    alerts_sent += 1

        logger.info(f"[Scheduler] Hourly check complete. Alerts sent: {alerts_sent}")
    except Exception as e:
        logger.error(f"[Scheduler] Hourly check error: {e}")


async def job_daily_report():
    """23:00 — Generate end-of-day report + send summary."""
    logger.info("[Scheduler] Generating daily report…")
    try:
        from automation.report_generator import generate_daily_report
        from automation.notifications import send_daily_summary
        from backend.database import AsyncSessionLocal
        from backend.analytics import compute_analytics

        file_path = await generate_daily_report()
        logger.info(f"[Scheduler] Report saved: {file_path}")

        async with AsyncSessionLocal() as db:
            analytics = await compute_analytics(db)
        await send_daily_summary({
            "total_bets": analytics.total_bets,
            "won": analytics.won,
            "lost": analytics.lost,
            "hit_rate": analytics.hit_rate,
            "total_profit": analytics.total_profit,
            "roi": analytics.roi,
            "total_staked": analytics.total_staked,
        })
    except Exception as e:
        logger.error(f"[Scheduler] Daily report error: {e}")


# ─── Scheduler factory ────────────────────────────────────────────────────────

def start_scheduler() -> AsyncIOScheduler:
    """Create, configure, and start the APScheduler instance."""
    scheduler = AsyncIOScheduler(timezone=utc)

    # Daily scan at 06:00 UTC
    scheduler.add_job(
        job_daily_scan,
        trigger=CronTrigger(hour=6, minute=0, timezone=utc),
        id="daily_scan",
        name="Daily fixture fetch + value scan",
        replace_existing=True,
        misfire_grace_time=3600,
    )

    # Hourly line movement check
    scheduler.add_job(
        job_hourly_check,
        trigger=IntervalTrigger(hours=1),
        id="hourly_check",
        name="Hourly line movement monitor",
        replace_existing=True,
        misfire_grace_time=300,
    )

    # Daily report at 23:00 UTC
    scheduler.add_job(
        job_daily_report,
        trigger=CronTrigger(hour=23, minute=0, timezone=utc),
        id="daily_report",
        name="EOD report generation",
        replace_existing=True,
        misfire_grace_time=3600,
    )

    scheduler.start()
    logger.info("APScheduler started with 3 jobs.")
    return scheduler
