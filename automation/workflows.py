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
from datetime import datetime, timedelta



# ─── Job functions ────────────────────────────────────────────────────────────

async def job_daily_scan():
    """06:00 — Fetch new fixtures and run value bet model scan."""
    logger.info("[Scheduler] Running daily scan…")
    try:
        from scrapers.odds_scraper import scrape_all_bookmakers
        from scrapers.data_fetch import fetch_fixtures, normalise_fixture, get_active_source
        from models.value_model import detect_value_bets_for_upcoming
        from backend.database import AsyncSessionLocal
        from backend.models import Match, League, Team
        from sqlalchemy import select
        import json

        # Fetch and store upcoming fixtures
        raw_fixtures = await fetch_fixtures(league_id=39, season=2024)
        source = get_active_source()
        async with AsyncSessionLocal() as db:
            for raw in raw_fixtures[:50]:
                norm = normalise_fixture(raw, source)
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
        
        # Phase 3: Generate recommendations immediately after scan
        if count > 0:
            await job_generate_recommendations()
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


async def job_xg_and_strengths():
    """Daily — Process xG data and update team strengths."""
    from automation.xg_processor import process_all_leagues_xg
    await process_all_leagues_xg()


async def job_track_clv():
    """Every 10 mins — Track closing odds for recently started matches."""
    from automation.clv_tracker import track_closing_odds
    await track_closing_odds()


async def job_generate_recommendations():
    """Phase 3: Categorize pending ValueBets into recommendations."""
    logger.info("[Scheduler] Generating recommendations…")
    try:
        from backend.database import AsyncSessionLocal
        from backend.models import ValueBet, Recommendation, Match
        from sqlalchemy import select
        from datetime import datetime

        async with AsyncSessionLocal() as db:
            # 1. Get all pending value bets that don't have a recommendation yet
            # We check the relationship or just existence of a record in recommendations table
            stmt = select(ValueBet).where(
                ValueBet.status == "pending",
                ValueBet.is_stale == False
            )
            result = await db.execute(stmt)
            bets = result.scalars().all()
            
            rec_count = 0
            for bet in bets:
                # Check if recommendation already exists for this value_bet_id
                check_stmt = select(Recommendation).where(Recommendation.value_bet_id == bet.id)
                existing = (await db.execute(check_stmt)).scalar_one_or_none()
                if existing: continue

                # Categorization logic
                ev = bet.ev
                score = bet.intelligence_score or 0.0
                
                # We'd ideally need the overround here, but for simplicity we'll use EV/Score
                # In a real scenario, we'd fetch the match and latest odds again or store overround in ValueBet
                
                category = "Avoid"
                reason = "Low intelligence score or high risk."
                
                if score > 0.8 and ev > 0.15:
                    category = "Sniper"
                    reason = "High EV and high model confidence. Priority bet."
                elif score > 0.6 and ev > 0.05:
                    category = "Safe"
                    reason = "Stable value with good model agreement."
                elif ev > 0.10:
                    category = "Aggressive"
                    reason = "High potential return but lower model stability."
                
                if score < 0.3:
                    category = "Avoid"
                    reason = "Model disagreement or high market efficiency."

                rec = Recommendation(
                    match_id=bet.match_id,
                    value_bet_id=bet.id,
                    category=category,
                    score=score,
                    reason=reason
                )
                db.add(rec)
                rec_count += 1
            
            await db.commit()
            if rec_count > 0:
                logger.info(f"[Scheduler] Generated {rec_count} recommendations.")
    except Exception as e:
        logger.error(f"[Scheduler] Recommendation generation error: {e}")


async def job_monitor_news_weather():
    """Every 30 mins — Poll for injuries and weather updates."""
    logger.info("[Scheduler] Checking news and weather…")
    try:
        from automation.news_monitor import monitor_team_news
        await monitor_team_news()
    except Exception as e:
        logger.error(f"[Scheduler] News monitor job error: {e}")


async def job_check_stale_odds():
    """Every 30 mins — Flag any odds older than 2 hours as 'stale'."""
    logger.info("[Scheduler] Running stale odds check…")
    try:
        from backend.database import AsyncSessionLocal
        from backend.models import ValueBet, OddsHistory
        from automation.notifications import send_telegram_message
        from sqlalchemy import select, update
        from datetime import datetime, timedelta

        now = datetime.utcnow()
        stale_threshold = now - timedelta(hours=2)

        async with AsyncSessionLocal() as db:
            # 1. Update ValueBets where the linked OddsHistory is old
            # Note: We need to join with OddsHistory to check the fetch time
            # For simplicity, we'll check ValueBets detected_at if they don't have a direct link to a specific OddsHistory record ID
            # Assuming detected_at is roughly when odds were fetched or slightly after
            
            # Find ValueBets that are older than 2 hours and not already stale
            stmt = select(ValueBet).where(
                ValueBet.status == "pending",
                ValueBet.is_stale == False,
                ValueBet.detected_at < stale_threshold
            )
            result = await db.execute(stmt)
            stale_bets = result.scalars().all()
            
            count = 0
            for bet in stale_bets:
                bet.is_stale = True
                count += 1
                # Alert for high EV bets that went stale
                if bet.ev > 0.1:
                    await send_telegram_message(
                        f"⚠️ Stale Odds Alert: ValueBet on {bet.match_id} ({bet.selection}) is now stale. (EV: {bet.ev:.2f})"
                    )
            
            await db.commit()
            if count > 0:
                logger.info(f"[Scheduler] Flagged {count} value bets as stale.")
    except Exception as e:
        logger.error(f"[Scheduler] Stale odds check error: {e}")


async def get_consecutive_losses() -> int:
    """Phase 4: Count consecutive losses from settled bets."""
    try:
        from backend.database import AsyncSessionLocal
        from backend.models import Bet
        from sqlalchemy import select
        
        async with AsyncSessionLocal() as db:
            stmt = select(Bet).where(Bet.result != "pending").order_by(Bet.settled_at.desc())
            result = await db.execute(stmt)
            bets = result.scalars().all()
            
            losses = 0
            for bet in bets:
                if bet.result == "lost":
                    losses += 1
                elif bet.result == "won":
                    break
            return losses
    except Exception as e:
        logger.error(f"Error getting consecutive losses: {e}")
        return 0


async def check_daily_loss_limit() -> bool:
    """Phase 4: Check if daily loss limit (SystemConfig) has been reached."""
    try:
        from backend.database import AsyncSessionLocal
        from backend.models import Bet, SystemConfig
        from sqlalchemy import select, func
        from datetime import datetime, time
        
        async with AsyncSessionLocal() as db:
            # 1. Get limit from config
            cfg_stmt = select(SystemConfig).where(SystemConfig.key == "max_daily_loss")
            cfg = (await db.execute(cfg_stmt)).scalar_one_or_none()
            limit = float(cfg.value) if cfg else 500.0 # Default limit
            
            # 2. Sum today's losses
            today_start = datetime.combine(datetime.utcnow().date(), time.min)
            stmt = select(Bet).where(Bet.settled_at >= today_start, Bet.result != "pending")
            result = await db.execute(stmt)
            bets = result.scalars().all()
            
            daily_pnl = sum((bet.actual_payout - bet.stake) for bet in bets)
            if daily_pnl <= -limit:
                logger.warning(f"Daily loss limit reached: {daily_pnl:.2f} <= -{limit}")
                return True
            return False
    except Exception as e:
        logger.error(f"Error checking daily loss limit: {e}")
        return False



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

    # xG and Strength Updates at 07:00 UTC
    scheduler.add_job(
        job_xg_and_strengths,
        trigger=CronTrigger(hour=7, minute=0, timezone=utc),
        id="xg_updates",
        name="Daily xG and team strength updates",
        replace_existing=True,
    )

    # CLV Tracking every 10 minutes
    scheduler.add_job(
        job_track_clv,
        trigger=IntervalTrigger(minutes=10),
        id="clv_tracking",
        name="Closing line value tracking",
        replace_existing=True,
    )

    # News and Weather monitoring every 30 minutes
    scheduler.add_job(
        job_monitor_news_weather,
        trigger=IntervalTrigger(minutes=30),
        id="news_weather",
        name="Team news and weather monitor",
        replace_existing=True,
    )

    # Stale Odds Check every 30 minutes
    scheduler.add_job(
        job_check_stale_odds,
        trigger=IntervalTrigger(minutes=30),
        id="stale_odds",
        name="Stale odds detector",
        replace_existing=True,
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
    logger.info("APScheduler started with 6 jobs.")
    return scheduler

