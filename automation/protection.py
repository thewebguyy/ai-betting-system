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
        from backend.models import SystemConfig
        from sqlalchemy.dialects.postgresql import insert as pg_insert 
        
        # Helper to upsert config
        async def set_config(k, v):
            # For cross-DB support (since we might be on SQLite locally)
            stmt = select(SystemConfig).where(SystemConfig.key == k)
            res = await db.execute(stmt)
            obj = res.scalar_one_or_none()
            if obj:
                obj.value = str(v)
            else:
                db.add(SystemConfig(key=k, value=str(v)))

        if drawdown >= 0.30:
            logger.warning(f"CRITICAL DRAWDOWN: {drawdown:.2%}. Pausing betting.")
            await set_config("betting_paused", "True")
            await set_config("kelly_fraction_multiplier", "0.0")
        elif drawdown >= 0.20:
            logger.warning(f"MODERATE DRAWDOWN: {drawdown:.2%}. Reducing Kelly fraction.")
            await set_config("betting_paused", "False")
            await set_config("kelly_fraction_multiplier", "0.5") # Reduce by half
        else:
            await set_config("betting_paused", "False")
            await set_config("kelly_fraction_multiplier", "1.0")
            
        await db.commit()

            
async def record_bankroll_snapshot(balance: float, note: str = ""):
    """
    Record current bankroll for drawdown tracking.
    """
    async with AsyncSessionLocal() as db:
        snapshot = Bankroll(balance=balance, note=note)
        db.add(snapshot)
        await db.commit()
    
    await check_drawdown_protection()
