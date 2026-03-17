"""
backend/database.py
Async SQLAlchemy engine + session factory + table bootstrap.
"""

import os
from pathlib import Path
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import text

from loguru import logger
from backend.config import get_settings


settings = get_settings()

# Ensure db directory exists
Path("db").mkdir(parents=True, exist_ok=True)
Path("logs").mkdir(parents=True, exist_ok=True)
Path("reports").mkdir(parents=True, exist_ok=True)
Path("models/cache").mkdir(parents=True, exist_ok=True)

db_url = settings.database_url
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql+asyncpg://", 1)
elif db_url.startswith("postgresql://"):
    if "+asyncpg" not in db_url:
        db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)

engine = create_async_engine(
    db_url,
    echo=settings.app_env == "development",
    connect_args={"check_same_thread": False} if "sqlite" in db_url else {},
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncSession:  # type: ignore[misc]
    """FastAPI dependency — yields an async DB session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db():
    """Bootstrap tables using SQLAlchemy metadata."""
    try:
        from asyncio import wait_for
        async with engine.begin() as conn:
            # Import models to register them
            from backend import models  # noqa: F401
            # Add a timeout to avoid hanging startup forever if DB is down
            await wait_for(conn.run_sync(Base.metadata.create_all), timeout=10.0)
        logger.info("Database tables initialised.")
    except Exception as e:
        logger.error(f"Database initialisation failed: {e}")
        logger.warning("App will attempt to start but DB operations might fail.")


