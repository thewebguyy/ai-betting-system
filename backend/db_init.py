"""
backend/db_init.py
Standalone script to initialise the database (run before starting the server).
Usage: python -m backend.db_init
"""

import asyncio
from loguru import logger
from backend.database import init_db


async def main():
    logger.info("Initialising database…")
    await init_db()
    logger.info("Database ready.")


if __name__ == "__main__":
    asyncio.run(main())
