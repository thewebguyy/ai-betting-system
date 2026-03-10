"""
backend/database.py
Async SQLAlchemy engine + session factory + table bootstrap.
"""

import os
from pathlib import Path
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import text

from backend.config import get_settings

settings = get_settings()

# Ensure db directory exists
Path("db").mkdir(parents=True, exist_ok=True)
Path("logs").mkdir(parents=True, exist_ok=True)
Path("reports").mkdir(parents=True, exist_ok=True)
Path("models/cache").mkdir(parents=True, exist_ok=True)

engine = create_async_engine(
    settings.database_url,
    echo=settings.app_env == "development",
    connect_args={"check_same_thread": False} if "sqlite" in settings.database_url else {},
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
    """Run raw SQL schema file to bootstrap tables."""
    schema_path = Path("db/schema.sql")
    if not schema_path.exists():
        return
    schema_sql = schema_path.read_text()
    # Split by statement (crude but works for this schema)
    statements = [s.strip() for s in schema_sql.split(";") if s.strip()]
    async with engine.begin() as conn:
        for stmt in statements:
            try:
                await conn.execute(text(stmt))
            except Exception as e:
                # Ignore "already exists" errors
                if "already exists" not in str(e).lower():
                    raise
