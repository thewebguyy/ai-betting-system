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
    result = await db.execute(select(Bet))
    bets = result.scalars().all()

    if not bets:
        return AnalyticsOut(
            total_bets=0, won=0, lost=0, void=0, pending=0,
            total_staked=0, total_profit=0, roi=0, yield_pct=0,
            hit_rate=0, avg_odds=0,
        )

    df = pd.DataFrame([{
        "stake": b.stake,
        "actual_payout": b.actual_payout,
        "result": b.result,
        "decimal_odds": b.decimal_odds,
    } for b in bets])

    total = len(df)
    won = int((df["result"] == "won").sum())
    lost = int((df["result"] == "lost").sum())
    void = int((df["result"] == "void").sum())
    pending = int((df["result"] == "pending").sum())

    settled = df[df["result"].isin(["won", "lost", "void"])]
    total_staked = float(settled["stake"].sum())
    total_profit = float((settled["actual_payout"] - settled["stake"]).sum())

    roi = (total_profit / total_staked * 100) if total_staked > 0 else 0.0
    yield_pct = roi  # For flat-staking yield == ROI
    hit_rate = (won / (won + lost) * 100) if (won + lost) > 0 else 0.0
    avg_odds = float(df["decimal_odds"].mean()) if not df.empty else 0.0

    return AnalyticsOut(
        total_bets=total,
        won=won, lost=lost, void=void, pending=pending,
        total_staked=round(total_staked, 2),
        total_profit=round(total_profit, 2),
        roi=round(roi, 2),
        yield_pct=round(yield_pct, 2),
        hit_rate=round(hit_rate, 2),
        avg_odds=round(avg_odds, 3),
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
