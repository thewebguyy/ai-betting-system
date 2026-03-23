"""
automation/xg_processor.py
Processes xG data from Understat and updates team strengths.
"""

from loguru import logger
from sqlalchemy import select, update, func
from backend.database import AsyncSessionLocal
from backend.models import Team, Match, TeamMatchStats, League
from backend.utils import is_same_team
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
            all_teams_res = await db.execute(select(Team))
            all_teams = all_teams_res.scalars().all()
            
            h_team = next((tx for tx in all_teams if is_same_team(tx.name, h_name)), None)
            a_team = next((tx for tx in all_teams if is_same_team(tx.name, a_name)), None)

            if h_team is not None and a_team is not None:
                # 2. Narrow types for the query
                h_id: int = h_team.id
                a_id: int = a_team.id

                # 3. Find the Match by date and teams
                match_res = await db.execute(select(Match).where(
                    Match.home_team_id == h_id,
                    Match.away_team_id == a_id,
                    func.date(Match.match_date) == match_date
                ))
                match = match_res.scalar_one_or_none()

                if match is not None:
                    m_id: int = match.id

                    # 4. Upsert stats for Home team
                    h_stats_res = await db.execute(select(TeamMatchStats).where(
                        TeamMatchStats.match_id == m_id,
                        TeamMatchStats.team_id == h_id
                    ))
                    h_stats = h_stats_res.scalar_one_or_none()
                    if not h_stats:
                        h_stats = TeamMatchStats(match_id=m_id, team_id=h_id)
                        db.add(h_stats)
                    h_stats.xg_for = h_xg
                    h_stats.xg_against = a_xg
                    h_stats.goals_for = h_goals
                    h_stats.goals_against = a_goals

                    # 5. Upsert stats for Away team
                    a_stats_res = await db.execute(select(TeamMatchStats).where(
                        TeamMatchStats.match_id == m_id,
                        TeamMatchStats.team_id == a_id
                    ))
                    a_stats = a_stats_res.scalar_one_or_none()
                    if not a_stats:
                        a_stats = TeamMatchStats(match_id=m_id, team_id=a_id)
                        db.add(a_stats)
                    a_stats.xg_for = a_xg
                    a_stats.xg_against = h_xg
                    a_stats.goals_for = a_goals
                    a_stats.goals_against = h_goals

        await db.commit()


async def recalculate_team_strengths():
    """
    Calculate attack/defence strengths with recency decay, normalized by league.
    """
    async with AsyncSessionLocal() as db:
        # 1. Fetch all leagues and calculate their specific xG averages
        leagues_res = await db.execute(select(League))
        leagues = leagues_res.scalars().all()
        
        league_averages = {}
        for lg in leagues:
            avg_res = await db.execute(
                select(func.avg(TeamMatchStats.xg_for))
                .join(Match, Match.id == TeamMatchStats.match_id)
                .where(Match.league_id == lg.id)
            )
            val = avg_res.scalar()
            league_averages[lg.id] = float(val) if val is not None else 1.35

        # 2. Update each team's strengths relative to its league average
        teams_result = await db.execute(select(Team))
        teams = teams_result.scalars().all()
        
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
            
            # Weighting: recency decay
            weights = [1.0 - (i * 0.05) for i in range(len(rows))] # Slower decay
            total_weight = sum(weights)
            
            weighted_xg_for = sum(r.xg_for * w for r, w in zip(rows, weights)) / total_weight
            weighted_xg_against = sum(r.xg_against * w for r, w in zip(rows, weights)) / total_weight
            
            # Use league-specific benchmark
            lg_id = team.league_id
            league_avg_xg = league_averages.get(lg_id, 1.35)
            
            # Strength = team_avg / league_avg
            team.attack_strength = round(weighted_xg_for / league_avg_xg, 4)
            team.defence_strength = round(weighted_xg_against / league_avg_xg, 4)
            
        await db.commit()
    logger.info("Team strengths recalculated with league-aware normalization.")
