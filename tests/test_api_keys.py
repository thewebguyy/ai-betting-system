
import asyncio
import httpx
import os
import sys
from loguru import logger

# Add project root to path for internal imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from backend.config import get_settings
from models.ai_layer import call_gemini, call_claude, call_deepseek

settings = get_settings()

async def test_api_football():
    """Test API-Football (RapidAPI) connection."""
    if not settings.api_football_key:
        return "MISSING", "API_FOOTBALL_KEY not set"
    
    headers = {
        "X-RapidAPI-Key": settings.api_football_key,
        "X-RapidAPI-Host": settings.rapidapi_host_football,
    }
    url = f"https://{settings.rapidapi_host_football}/v3/leagues"
    params = {"id": 39} # Premier League
    
    try:
        async with httpx.AsyncClient(headers=headers, timeout=10.0) as client:
            resp = await client.get(url, params=params)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("response"):
                    return "SUCCESS", "Connected and fetched Premier League info"
                else:
                    return "ERROR", f"Empty response: {data}"
            else:
                return "FAILED", f"HTTP {resp.status_code}: {resp.text[:100]}"
    except Exception as e:
        return "ERROR", f"Crashed: {str(e)}"

async def test_odds_api():
    """Test The Odds API connection."""
    if not settings.odds_api_key:
        return "MISSING", "ODDS_API_KEY not set"
    
    url = "https://api.the-odds-api.com/v4/sports"
    params = {"apiKey": settings.odds_api_key}
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, params=params)
            if resp.status_code == 200:
                remaining = resp.headers.get("x-requests-remaining", "?")
                return "SUCCESS", f"Connected. Quota remaining: {remaining}"
            else:
                return "FAILED", f"HTTP {resp.status_code}: {resp.text[:100]}"
    except Exception as e:
        return "ERROR", f"Crashed: {str(e)}"

async def test_gemini():
    """Test Google Gemini connection."""
    if not settings.gemini_api_key:
        return "MISSING", "GEMINI_API_KEY not set"
    
    # call_gemini already handles the call via LangChain
    res = await call_gemini("Translate this message to one word: 'READY'")
    if "READY" in res.upper():
        return "SUCCESS", "Gemini responded successfully"
    elif "[Gemini error" in res:
        return "FAILED", res
    else:
        return "ERROR", f"Unexpected response: {res[:50]}..."

async def test_claude():
    """Test Anthropic Claude connection."""
    if not settings.anthropic_api_key:
        return "MISSING", "ANTHROPIC_API_KEY not set"
    
    res = await call_claude("Translate this message to one word: 'READY'")
    if "READY" in res.upper():
        return "SUCCESS", "Claude responded successfully"
    elif "[Claude error" in res:
        return "FAILED", res
    else:
        return "ERROR", f"Unexpected response: {res[:50]}..."

async def test_deepseek():
    """Test DeepSeek connection."""
    if not settings.deepseek_api_key:
        return "MISSING", "DEEPSEEK_API_KEY not set"
    
    res = await call_deepseek("Translate this message to one word: 'READY'")
    if "READY" in res.upper():
        return "SUCCESS", "DeepSeek responded successfully"
    elif "[DeepSeek error" in res:
        return "FAILED", res
    else:
        return "ERROR", f"Unexpected response: {res[:50]}..."

async def test_telegram():
    """Test Telegram Bot Token."""
    if not settings.telegram_bot_token:
        return "MISSING", "TELEGRAM_BOT_TOKEN not set"
    
    url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/getMe"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url)
            if resp.status_code == 200:
                data = resp.json()
                bot_name = data.get("result", {}).get("username", "Unknown")
                return "SUCCESS", f"Connected as @{bot_name}"
            else:
                return "FAILED", f"HTTP {resp.status_code}: {resp.text[:100]}"
    except Exception as e:
        return "ERROR", f"Crashed: {str(e)}"

async def test_sendgrid():
    """Test SendGrid API Key."""
    if not settings.sendgrid_api_key:
        return "MISSING", "SENDGRID_API_KEY not set"
    
    # We can use API keys endpoint to see if they are valid
    url = "https://api.sendgrid.com/v3/api_keys"
    headers = {"Authorization": f"Bearer {settings.sendgrid_api_key}"}
    try:
        async with httpx.AsyncClient(headers=headers, timeout=10.0) as client:
            resp = await client.get(url)
            if resp.status_code == 200:
                return "SUCCESS", "SendGrid key is valid (able to list subkeys)"
            elif resp.status_code == 401:
                 return "FAILED", "Unauthorized (invalid key)"
            else:
                return "WARNING", f"HTTP {resp.status_code}: {resp.text[:100]}"
    except Exception as e:
        return "ERROR", f"Crashed: {str(e)}"

async def main():
    print("\n" + "="*50)
    print("      AI BETTING SYSTEM - API KEY VALIDATOR")
    print("="*50 + "\n")
    
    tests = [
        ("API-Football", test_api_football),
        ("The Odds API", test_odds_api),
        ("Google Gemini", test_gemini),
        ("Anthropic Claude", test_claude),
        ("DeepSeek AI", test_deepseek),
        ("Telegram Bot", test_telegram),
        ("SendGrid Email", test_sendgrid),
    ]
    
    success_count = 0
    missing_count = 0
    failed_count = 0
    
    for name, func in tests:
        print(f"[*] Testing {name:15}... ", end="", flush=True)
        status, msg = await func()
        
        if status == "SUCCESS":
            print(f"✅ SUCCESS - {msg}")
            success_count += 1
        elif status == "MISSING":
            print(f"⚪ MISSING - {msg}")
            missing_count += 1
        elif status == "FAILED":
            print(f"❌ FAILED  - {msg}")
            failed_count += 1
        else:
            print(f"⚠️ ERROR   - {msg}")
            failed_count += 1

    print("\n" + "="*50)
    print(f"SUMMARY: {success_count} Passed, {failed_count} Failed, {missing_count} Missing")
    print("="*50 + "\n")
    
    if missing_count > 0:
        print("💡 TIP: Copy .env.example to .env and fill in your keys.\n")

if __name__ == "__main__":
    # Suppress loguru output if we want a clean report, or let it be
    # import sys
    # logger.remove()
    # logger.add(sys.stderr, level="ERROR")
    
    asyncio.run(main())
