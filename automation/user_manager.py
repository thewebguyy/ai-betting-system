"""
automation/user_manager.py
User and tier management for the Telegram Bot.
"""

from loguru import logger
from datetime import datetime
from typing import Optional
from backend.database import AsyncSessionLocal
from backend.models import User
from backend.config import get_settings
from sqlalchemy import select, update

settings = get_settings()

async def get_or_create_user(telegram_id: str, username: Optional[str] = None) -> User:
    """Upsert User row and update last_seen_at."""
    try:
        async with AsyncSessionLocal() as db:
            stmt = select(User).where(User.telegram_id == str(telegram_id))
            result = await db.execute(stmt)
            user = result.scalar_one_or_none()
            
            if not user:
                user = User(
                    telegram_id=str(telegram_id),
                    username=username,
                    tier="free",
                    is_active=True,
                    registered_at=datetime.utcnow(),
                    last_seen_at=datetime.utcnow()
                )
                db.add(user)
                logger.info(f"New user registered: {telegram_id} ({username})")
            else:
                user.last_seen_at = datetime.utcnow()
                if username:
                    user.username = username
            
            await db.commit()
            await db.refresh(user)
            return user
    except Exception as e:
        logger.error(f"Error in get_or_create_user: {e}")
        # Return a transient user object if DB fails to avoid bot crash
        return User(telegram_id=telegram_id, username=username, tier="free", is_active=True)

async def get_user_tier(telegram_id: str) -> str:
    """Return tier string for a given telegram_id, default 'free'."""
    try:
        async with AsyncSessionLocal() as db:
            stmt = select(User).where(User.telegram_id == str(telegram_id))
            result = await db.execute(stmt)
            user = result.scalar_one_or_none()
            return user.tier if user else "free"
    except Exception as e:
        logger.error(f"Error in get_user_tier: {e}")
        return "free"

async def set_user_tier(telegram_id: str, tier: str) -> bool:
    """Admin-only update, validates tier value."""
    if tier not in ["free", "starter", "pro", "syndicate"]:
        logger.warning(f"Invalid tier: {tier}")
        return False
    try:
        async with AsyncSessionLocal() as db:
            stmt = update(User).where(User.telegram_id == str(telegram_id)).values(tier=tier)
            await db.execute(stmt)
            await db.commit()
            logger.info(f"User {telegram_id} tier updated to {tier}")
            return True
    except Exception as e:
        logger.error(f"Error in set_user_tier: {e}")
        return False

def get_tier_limit(tier: str) -> int:
    """Returns the int daily limit for a tier from settings."""
    if tier == "free":
        return settings.free_daily_limit
    elif tier == "starter":
        return settings.starter_daily_limit
    elif tier == "pro" or tier == "syndicate":
        return settings.pro_daily_limit
    return settings.free_daily_limit
