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
    async with engine.begin() as conn:
        # This will create tables if they don't exist based on the models
        # It's more robust than raw SQL for cross-db (SQLite/Postgres) support.
        # We import models here to ensure they are registered with Base.metadata
        from backend import models  # noqa: F401
        await conn.run_sync(Base.metadata.create_all)
    
    logger.info("Database tables initialised.")

