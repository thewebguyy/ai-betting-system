"""
automation/xg_processor.py
Processes xG data from Understat and updates team strengths.
"""

from loguru import logger
from sqlalchemy import select, update, func
from backend.database import AsyncSessionLocal
from backend.models import Team, Match, TeamMatchStats
from scrapers.understat_scraper import fetch_understat_league_results
from datetime import datetime, timedelta

LEAGUE_MAPPING = {
    "EPL": "EPL",
    "La_Liga": "La_Liga",
    "Bundesliga": "Bundesliga",
    "Serie_A": "Serie_A",
    "Ligue_1": "Ligue_1",
}

async def process_all_leagues_xg():
    """
    Fetch xG for all supported leagues and update team strengths.
    """
    for understat_name in LEAGUE_MAPPING.values():
        logger.info(f"Processing xG for {understat_name}…")
        try:
            results = await fetch_understat_league_results(understat_name)
            await update_xg_stats(results)
        except Exception as e:
            logger.error(f"Error processing xG for {understat_name}: {e}")
    
    await recalculate_team_strengths()

async def update_xg_stats(results: list):
    """
    Update TeamMatchStats with results from Understat.
    """
    async with AsyncSessionLocal() as db:
        for res in results:
            if not res.get('isResult'):
                continue
                
            match_date = datetime.strptime(res['datetime'], '%Y-%m-%d %H:%M:%S').date()
            h_name = res['h']['title']
            a_name = res['a']['title']
            h_xg = float(res['xG']['h'])
            a_xg = float(res['xG']['a'])
            h_goals = int(res['goals']['h'])
            a_goals = int(res['goals']['a'])

            # 1. Find the teams in our DB
            from backend.models import Team
            h_team = (await db.execute(select(Team).where(
                (Team.name.ilike(f"%{h_name}%")) | (Team.name.ilike(f"%{h_name.split(' ')[0]}%"))
            ))).scalar_one_or_none()
            
            a_team = (await db.execute(select(Team).where(
                (Team.name.ilike(f"%{a_name}%")) | (Team.name.ilike(f"%{a_name.split(' ')[0]}%"))
            ))).scalar_one_or_none()

            if not h_team or not a_team:
                continue

            # 2. Find the Match by date and teams
            match = (await db.execute(select(Match).where(
                Match.home_team_id == h_team.id,
                Match.away_team_id == a_team.id,
                func.date(Match.match_date) == match_date
            ))).scalar_one_or_none()

            if not match:
                continue

            # 3. Upsert stats for Home team
            h_stats = (await db.execute(select(TeamMatchStats).where(
                TeamMatchStats.match_id == match.id,
                TeamMatchStats.team_id == h_team.id
            ))).scalar_one_or_none()
            if not h_stats:
                h_stats = TeamMatchStats(match_id=match.id, team_id=h_team.id)
                db.add(h_stats)
            h_stats.xg_for = h_xg
            h_stats.xg_against = a_xg
            h_stats.goals_for = h_goals
            h_stats.goals_against = a_goals

            # 4. Upsert stats for Away team
            a_stats = (await db.execute(select(TeamMatchStats).where(
                TeamMatchStats.match_id == match.id,
                TeamMatchStats.team_id == a_team.id
            ))).scalar_one_or_none()
            if not a_stats:
                a_stats = TeamMatchStats(match_id=match.id, team_id=a_team.id)
                db.add(a_stats)
            a_stats.xg_for = a_xg
            a_stats.xg_against = h_xg
            a_stats.goals_for = a_goals
            a_stats.goals_against = h_goals

        await db.commit()


async def recalculate_team_strengths():
    """
    Calculate attack/defence strengths with recency decay.
    """
    async with AsyncSessionLocal() as db:
        teams_result = await db.execute(select(Team))
        teams = teams_result.scalars().all()
        
        # Get league averages first
        avg_result = await db.execute(
            select(func.avg(TeamMatchStats.xg_for))
        )
        league_avg_xg = avg_result.scalar() or 1.3
        
        for team in teams:
            # Get last 10 matches for this team
            stats_result = await db.execute(
                select(TeamMatchStats)
                .where(TeamMatchStats.team_id == team.id)
                .order_by(TeamMatchStats.created_at.desc())
                .limit(10)
            )
            rows = stats_result.scalars().all()
            if not rows: continue
            
            # Weighting: 1.0 for most recent, decreasing by 0.1 for each previous
            weights = [1.0 - (i * 0.1) for i in range(len(rows))]
            total_weight = sum(weights)
            
            weighted_xg_for = sum(r.xg_for * w for r, w in zip(rows, weights)) / total_weight
            weighted_xg_against = sum(r.xg_against * w for r, w in zip(rows, weights)) / total_weight
            
            # Strength = team_avg / league_avg
            team.attack_strength = round(weighted_xg_for / league_avg_xg, 4)
            team.defence_strength = round(weighted_xg_against / league_avg_xg, 4)
            
        await db.commit()
    logger.info("Team strengths recalculated with recency decay.")
