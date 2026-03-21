"""
automation/run_bot.py
Entry point for the Telegram Bot subprocess.
"""

import asyncio
from automation.telegram_bot import run_telegram_bot

if __name__ == "__main__":
    try:
        asyncio.run(run_telegram_bot())
    except KeyboardInterrupt:
        pass
