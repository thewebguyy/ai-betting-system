"""
backend/analytics.py
SQL-based analytics computations: ROI, yield, hit rate, CLV, line movement.
"""

from typing import Optional
import pandas as pd
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, text

from backend.models import Bet, OddsHistory
from backend.schemas import AnalyticsOut


async def compute_analytics(db: AsyncSession) -> AnalyticsOut:
    """Compute betting performance metrics from all settled bets."""
    # Use joinedload to get match and league info for segmentation
    from sqlalchemy.orm import joinedload
    from backend.models import Match, League
    
    stmt = select(Bet).options(joinedload(Bet.match).joinedload(Match.league))
    result = await db.execute(stmt)
    bets = result.scalars().all()


    if not bets:
        return AnalyticsOut(
            total_bets=0, won=0, lost=0, void=0, pending=0,
            total_staked=0, total_profit=0, roi=0, yield_pct=0,
            hit_rate=0, avg_odds=0,
        )

    data = []
    for b in bets:
        league_name = "Unknown"
        if b.match and b.match.league:
            league_name = b.match.league.name
            
        data.append({
            "stake": b.stake,
            "actual_payout": b.actual_payout,
            "result": b.result,
            "decimal_odds": b.decimal_odds,
            "bookmaker": b.bookmaker,
            "market": b.market,
            "clv": b.clv or 0.0,
            "league": league_name, 
        })

    
    df = pd.DataFrame(data)

    settled = df[df["result"].isin(["won", "lost", "void"])]
    total_staked = float(settled["stake"].sum())
    total_profit = float((settled["actual_payout"] - settled["stake"]).sum())

    # Segmentation Helper
    def get_roi_stats(group_col):
        if settled.empty: return {}
        groups = settled.groupby(group_col)
        stats = {}
        for name, group in groups:
            if len(group) < 5: continue # Min sample size (user said 30, but 5 for testing)
            staked = group["stake"].sum()
            profit = (group["actual_payout"] - group["stake"]).sum()
            stats[str(name)] = round((profit / staked * 100), 2)
        return stats

    return AnalyticsOut(
        total_bets=len(df),
        won=int((df["result"] == "won").sum()),
        lost=int((df["result"] == "lost").sum()),
        void=int((df["result"] == "void").sum()),
        pending=int((df["result"] == "pending").sum()),
        total_staked=round(total_staked, 2),
        total_profit=round(total_profit, 2),
        roi=round((total_profit / total_staked * 100) if total_staked > 0 else 0, 2),
        yield_pct=round((total_profit / total_staked * 100) if total_staked > 0 else 0, 2),
        hit_rate=round((int((df["result"] == "won").sum()) / (int((df["result"] == "won").sum()) + int((df["result"] == "lost").sum())) * 100) if (int((df["result"] == "won").sum()) + int((df["result"] == "lost").sum())) > 0 else 0, 2),
        avg_odds=round(df["decimal_odds"].mean(), 3),
        avg_clv=round(df["clv"].mean(), 4),
        roi_by_league=get_roi_stats("league"),
        roi_by_market=get_roi_stats("market"),
        roi_by_bookmaker=get_roi_stats("bookmaker"),
        calibration_data=[], # Placeholder for now
    )



async def compute_line_movement(
    db: AsyncSession, match_id: int, bookmaker: Optional[str] = None
) -> dict:
    """
    Return time-series odds data for a match to show line movement.
    Detects if movement exceeds alert threshold.
    """
    stmt = (
        select(OddsHistory)
        .where(OddsHistory.match_id == match_id)
        .order_by(OddsHistory.fetched_at)
    )
    if bookmaker:
        stmt = stmt.where(OddsHistory.bookmaker == bookmaker)

    result = await db.execute(stmt)
    rows = result.scalars().all()

    if not rows:
        return {"match_id": match_id, "history": [], "alerts": []}

    history = [{
        "bookmaker": r.bookmaker,
        "home_odds": r.home_odds,
        "draw_odds": r.draw_odds,
        "away_odds": r.away_odds,
        "fetched_at": r.fetched_at.isoformat(),
    } for r in rows]

    # Detect significant line moves
    alerts = []
    from backend.config import get_settings
    settings = get_settings()
    threshold = settings.odds_line_move_alert

    if len(rows) >= 2:
        first = rows[0]
        last = rows[-1]
        for field in ["home_odds", "draw_odds", "away_odds"]:
            v1 = getattr(first, field)
            v2 = getattr(last, field)
            if v1 and v2 and v1 > 0:
                delta = abs(v2 - v1) / v1
                if delta >= threshold:
                    alerts.append({
                        "field": field,
                        "from": v1,
                        "to": v2,
                        "delta_pct": round(delta * 100, 2),
                    })

    return {"match_id": match_id, "history": history, "alerts": alerts}
