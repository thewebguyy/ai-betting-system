"""
automation/protection.py
Drawdown protection logic.
"""

from loguru import logger
from sqlalchemy import select, func
from backend.database import AsyncSessionLocal
from backend.models import Bankroll, Bet
from backend.config import get_settings

settings = get_settings()

async def check_drawdown_protection():
    """
    Check current bankroll against rolling peak and apply protection.
    """
    async with AsyncSessionLocal() as db:
        # Get historical balances
        result = await db.execute(
            select(Bankroll.balance).order_by(Bankroll.snapshot_at)
        )
        balances = [r[0] for r in result.all()]
        
        if not balances:
            return
            
        current = balances[-1]
        peak = max(balances)
        
        drawdown = (peak - current) / peak if peak > 0 else 0
        
        if drawdown >= 0.30:
            logger.warning(f"CRITICAL DRAWDOWN: {drawdown:.2%}. Pausing betting.")
            # Logic to set betting_paused = True in DB/Settings
        elif drawdown >= 0.20:
            logger.warning(f"MODERATE DRAWDOWN: {drawdown:.2%}. Reducing Kelly fraction.")
            # Logic to set kelly_fraction = 0.125
        else:
            # Normal operation
            pass
            
async def record_bankroll_snapshot(balance: float, note: str = ""):
    """
    Record current bankroll for drawdown tracking.
    """
    async with AsyncSessionLocal() as db:
        snapshot = Bankroll(balance=balance, note=note)
        db.add(snapshot)
        await db.commit()
    
    await check_drawdown_protection()
