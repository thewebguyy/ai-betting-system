import asyncio
import os
from scrapers.data_fetch import fetch_fixtures

async def test():
    try:
        res = await fetch_fixtures(league_id=39, season=2025, status="FT")
        print(f"Items: {len(res)}")
    except Exception as e:
        print(f"Failed: {e}")

if __name__ == "__main__":
    asyncio.run(test())
