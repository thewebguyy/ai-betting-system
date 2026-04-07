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

        # Top 5 European Leagues
        LEAGUES = [39, 140, 135, 78, 61] # EPL, La Liga, Serie A, Bundesliga, Ligue 1
        raw_fixtures = []
        for lid in LEAGUES:
             raw_fixtures += await fetch_fixtures(league_id=lid, season=2024)
        source = get_active_source()
        async with AsyncSessionLocal() as db:
            for fixture_data in raw_fixtures[:50]:
                norm = normalise_fixture(fixture_data, source)
                
                # 1. Upsert League
                league_api_id = norm.get("league_id")
                from backend.models import League, Team
                res_l = await db.execute(select(League).where(League.api_id == league_api_id))
                league = res_l.scalar_one_or_none()
                if not league:
                    league = League(api_id=league_api_id, name=f"League {league_api_id}", season=norm.get("season"))
                    db.add(league)
                    await db.flush()

                # 2. Upsert Home Team
                home_api_id = norm.get("home_team_api_id")
                res_h = await db.execute(select(Team).where(Team.api_id == home_api_id))
                home_team = res_h.scalar_one_or_none()
                if not home_team:
                    home_team = Team(api_id=home_api_id, name=norm.get("home_team"), league_id=league.id)
                    db.add(home_team)
                    await db.flush()

                # 3. Upsert Away Team
                away_api_id = norm.get("away_team_api_id")
                res_a = await db.execute(select(Team).where(Team.api_id == away_api_id))
                away_team = res_a.scalar_one_or_none()
                if not away_team:
                    away_team = Team(api_id=away_api_id, name=norm.get("away_team"), league_id=league.id)
                    db.add(away_team)
                    await db.flush()

                # 4. Upsert match
                result = await db.execute(
                    select(Match).where(Match.api_id == norm["api_id"])
                )
                existing = result.scalar_one_or_none()
                
                # Ensure date is parsed if it's a string
                m_date = norm["match_date"]
                if isinstance(m_date, str):
                    try:
                        from dateutil.parser import parse
                        m_date = parse(m_date)
                    except:
                        pass # Fallback to original string if parse fails

                if not existing:
                    match = Match(
                        api_id=norm["api_id"],
                        league_id=league.id,
                        home_team_id=home_team.id,
                        away_team_id=away_team.id,
                        match_date=m_date,
                        status="scheduled",
                        venue=norm.get("venue", ""),
                    )
                    db.add(match)
                else:
                    # Update existing match team IDs just in case they were missing
                    existing.home_team_id = home_team.id
                    existing.away_team_id = away_team.id
                    existing.league_id = league.id
            await db.commit()

        # Step 5: Seed xG data if needed (if no stats exist)
        from backend.models import TeamMatchStats
        from sqlalchemy import func
        async with AsyncSessionLocal() as db:
            count_res = await db.execute(select(func.count(TeamMatchStats.id)))
            if count_res.scalar() == 0:
                logger.info("[Scheduler] Seeding historical xG data from Understat…")
                from automation.xg_processor import process_all_leagues_xg
                await process_all_leagues_xg()

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
        
        # Measurement-First Reports
        from scripts.generate_research_reports import generate_clv_report, generate_lag_report, generate_edge_hypotheses_report
        generate_clv_report()
        generate_lag_report()
        generate_edge_hypotheses_report()
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
                # Phase 5: Refresh the brain cache for the Telegram bot
                from models.betting_brain import BettingBrain
                await BettingBrain.refresh_daily_cache()
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
        return 0 # Fallback if no bets found
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

    # Lag analysis every hour
    scheduler.add_job(
        job_lag_analysis,
        trigger=IntervalTrigger(hours=1),
        id="lag_analysis",
        name="Market lag detection",
        replace_existing=True,
    )
    
    # Hourly hypothesis auto-generation and pseudo-execution
    scheduler.add_job(
        job_hourly_hypothesis_update,
        trigger=IntervalTrigger(hours=1),
        id="hourly_hypothesis_update_job",
        name="Hourly Hypothesis Update",
        replace_existing=True,
    )
    
    # Hourly prediction feed refresh and WS broadcast
    scheduler.add_job(
        job_hourly_prediction_feed,
        trigger=IntervalTrigger(hours=1),
        id="hourly_prediction_feed_job",
        name="Hourly Prediction Feed Refresh",
        replace_existing=True,
    )

    # Daily edge summary compiling ranked hypotheses
    scheduler.add_job(
        job_daily_edge_summary,
        trigger=CronTrigger(hour=23, minute=30, timezone=utc),
        id="daily_edge_summary_job",
        name="Daily Edge Summary",
        replace_existing=True,
    )

async def job_hourly_prediction_feed():
    """Hourly background job to run the prediction feed and trigger dashboard refresh via WS."""
    from backend.app import app, get_today_predictions
    from backend.schemas import WSEvent
    from datetime import datetime
    logger.info("[Scheduler] Refreshing today's prediction feed and broadcasting WS event...")
    try:
        from backend.database import AsyncSessionLocal
        # Force a prediction feed refresh implicitly by calling the API logic
        # For simplicity, we trigger a WS alert that tells frontend to refresh
        ws_manager = getattr(app.state, 'ws_manager', None)
        if ws_manager:
            await ws_manager.broadcast(WSEvent(
                event_type="predictions_refreshed",
                timestamp=datetime.utcnow().isoformat(),
                data={"message": "New predictions calculated. Please reload."}
            ))
    except Exception as e:
        logger.error(f"[Scheduler] Prediction feed refresh error: {e}")

async def job_lag_analysis():
    """Analyze lags between sharp and local bookies."""
    from automation.lag_detector import analyze_all_recent_matches
    await analyze_all_recent_matches()

async def job_hourly_hypothesis_update():
    """Hourly check for new hypotheses and pseudo-execution simulation."""
    logger.info("[Scheduler] Running hourly hypothesis update...")
    try:
        from scripts.pseudo_execution import run_pseudo_execution_workflow
        run_pseudo_execution_workflow()
    except Exception as e:
        logger.error(f"[Scheduler] Hypothesis update error: {e}")

async def job_daily_edge_summary():
    """Daily compilation of ranked hypotheses and historical trends."""
    logger.info("[Scheduler] Generating daily edge summary report...")
    try:
        from scripts.generate_research_reports import generate_edge_hypotheses_report
        generate_edge_hypotheses_report()
    except Exception as e:
        logger.error(f"[Scheduler] Daily edge summary error: {e}")

def start_scheduler() -> AsyncIOScheduler:
    """Create, configure, and start the APScheduler instance."""
    scheduler = AsyncIOScheduler(timezone=utc)

    # 1. Daily Scan at 06:00 UTC
    scheduler.add_job(
        job_daily_scan,
        trigger=CronTrigger(hour=6, minute=0, timezone=utc),
        id="daily_scan",
        name="Daily fixtures and value scan",
        replace_existing=True,
        misfire_grace_time=3600,
    )

    # 2. Daily Report at 23:00 UTC
    scheduler.add_job(
        job_daily_report,
        trigger=CronTrigger(hour=23, minute=0, timezone=utc),
        id="daily_report",
        name="EOD report generation",
        replace_existing=True,
        misfire_grace_time=3600,
    )

    # 3. Daily Edge Summary at 23:30 UTC
    scheduler.add_job(
        job_daily_edge_summary,
        trigger=CronTrigger(hour=23, minute=30, timezone=utc),
        id="daily_edge_summary_job",
        name="Daily Edge Summary",
        replace_existing=True,
    )

    # 4. Hourly Line Movement monitor
    scheduler.add_job(
        job_hourly_odds_update,
        trigger=IntervalTrigger(hours=1),
        id="hourly_odds_update",
        name="Hourly line movement monitor",
        replace_existing=True,
        misfire_grace_time=300,
    )

    # 5. Hourly Lag Analysis
    scheduler.add_job(
        job_lag_analysis,
        trigger=IntervalTrigger(hours=1),
        id="lag_analysis",
        name="Market lag detection",
        replace_existing=True,
    )
    
    # 6. Hourly Prediction Feed Refresh
    scheduler.add_job(
        job_hourly_prediction_feed,
        trigger=IntervalTrigger(hours=1),
        id="hourly_prediction_feed_job",
        name="Hourly Prediction Feed Refresh",
        replace_existing=True,
    )

    scheduler.start()
    logger.info("APScheduler started with 6 jobs.")
    return scheduler

