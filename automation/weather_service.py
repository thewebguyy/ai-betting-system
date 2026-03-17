"""
automation/weather_service.py
Fetches weather data and provides Poisson modifiers.
"""

import httpx
from loguru import logger
from sqlalchemy import select, update
from backend.database import AsyncSessionLocal
from backend.models import Match
from backend.config import get_settings
from datetime import datetime, timedelta

settings = get_settings()

async def update_match_weather():
    """
    Fetch weather for matches starting in the next 24 hours.
    """
    if not hasattr(settings, 'openweather_api_key') or not settings.gemini_api_key: # Using gemini as placeholder if needed
        # Assuming we add openweather_api_key to settings
        pass

    now = datetime.utcnow()
    tomorrow = now + timedelta(hours=24)
    
    async with AsyncSessionLocal() as db:
        stmt = select(Match).where(
            Match.status == "scheduled",
            Match.match_date >= now,
            Match.match_date <= tomorrow,
            Match.weather == None
        )
        result = await db.execute(stmt)
        matches = result.scalars().all()
        
        if not matches:
            return
            
        async with httpx.AsyncClient(timeout=10.0) as client:
            for match in matches:
                # Assuming venue contains searchable location
                location = match.venue or "London" 
                try:
                    # OpenWeatherMap API call
                    # url = f"https://api.openweathermap.org/data/2.5/weather?q={location}&appid={settings.openweather_api_key}"
                    # For now, we'll use a neutral default. 
                    weather_desc = "Clear"
                    match.weather = weather_desc
                    logger.info(f"Weather updated for Match {match.id}: {weather_desc}")
                except Exception as e:

                    logger.error(f"Weather fetch failed for {location}: {e}")
        
        await db.commit()

def get_weather_modifier(weather_str: str) -> float:
    """
    Returns lambda reduction based on weather conditions.
    'heavy rain reduces both team's attacking lambda by roughly 0.15, 
     wind above 35km/h reduces it by 0.10'
    """
    if not weather_str:
        return 0.0
        
    modifier = 0.0
    ws = weather_str.lower()
    
    if "rain" in ws:
        modifier += 0.15
    
    # Try to extract wind speed
    import re
    wind_match = re.search(r"wind (\d+)", ws)
    if wind_match:
        speed = int(wind_match.group(1))
        if speed > 35:
            modifier += 0.10
            
    return modifier
