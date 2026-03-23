"""
tests/test_telegram_bot.py
Mocks Telegram updates to verify bot command handlers and tier gating.
"""

import pytest
import sys
import os
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

# Add project root to path for internal imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from telegram import Update, User as TGUser, Message, Chat
from telegram.ext import ContextTypes

from automation.telegram_bot import start, today, check, bankroll, explain
from backend.models import User

@pytest.fixture
def mock_update():
    """Create a mock Telegram Update objects."""
    update = MagicMock(spec=Update)
    update.effective_user = MagicMock(spec=TGUser)
    update.effective_user.id = 12345
    update.effective_user.first_name = "Test"
    update.effective_user.username = "testuser"
    
    update.message = AsyncMock(spec=Message)
    update.message.reply_text = AsyncMock()
    update.message.reply_html = AsyncMock()
    update.message.reply_chat_action = AsyncMock()
    return update

@pytest.fixture
def mock_context():
    context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
    context.args = []
    return context

@pytest.mark.asyncio
async def test_start_handler(mock_update, mock_context):
    """Verify /start registers user and sends welcome."""
    with patch("automation.telegram_bot.get_or_create_user", new_callable=AsyncMock) as mock_get_user:
        mock_get_user.return_value = User(telegram_id="12345", tier="free", is_active=True)
        
        await start(mock_update, mock_context)
        
        mock_get_user.assert_called_once()
        mock_update.message.reply_text.assert_called()
        args, _ = mock_update.message.reply_text.call_args
        assert "Welcome" in args[0]
        assert "FREE" in args[0]

@pytest.mark.asyncio
async def test_today_handler_free_tier(mock_update, mock_context):
    """Verify /today respects free tier limits."""
    with patch("automation.telegram_bot.get_or_create_user", new_callable=AsyncMock) as mock_get_user, \
         patch("automation.telegram_bot.BettingBrain.get_latest_intelligence", new_callable=AsyncMock) as mock_brain:
        
        mock_get_user.return_value = User(telegram_id="12345", tier="free", is_active=True)
        # Mock 3 safe bets
        mock_brain.return_value = {
            "safe_bets": [
                {"selection": "Bet 1", "bookmaker": "B1", "decimal_odds": 2.0, "uds_score": 80, "suggested_stake": 10},
                {"selection": "Bet 2", "bookmaker": "B2", "decimal_odds": 1.9, "uds_score": 75, "suggested_stake": 5},
                {"selection": "Bet 3", "bookmaker": "B3", "decimal_odds": 1.8, "uds_score": 70, "suggested_stake": 3},
            ],
            "bankroll": 1000
        }
        
        # Free limit is 1 (from our config edit)
        await today(mock_update, mock_context)
        
        mock_update.message.reply_html.assert_called()
        args, _ = mock_update.message.reply_html.call_args
        # Should only see 1 bet and a "hidden" message
        assert "1. ⚽ <b>Bet 1</b>" in args[0]
        assert "Bet 2" not in args[0]
        assert "more bets hidden" in args[0]

@pytest.mark.asyncio
async def test_explain_handler_locked_for_free(mock_update, mock_context):
    """Verify /explain is locked for free users."""
    with patch("automation.telegram_bot.get_or_create_user", new_callable=AsyncMock) as mock_get_user:
        mock_get_user.return_value = User(telegram_id="12345", tier="free", is_active=True)
        mock_context.args = ["Arsenal"]
        
        await explain(mock_update, mock_context)
        
        mock_update.message.reply_text.assert_called_with("🔒 /explain is a PRO feature. Upgrade to unlock AI reasoning briefs.")

@pytest.mark.asyncio
async def test_bankroll_handler(mock_update, mock_context):
    """Verify /bankroll scales stakes."""
    with patch("automation.telegram_bot.get_or_create_user", new_callable=AsyncMock) as mock_get_user, \
         patch("automation.telegram_bot.BettingBrain.get_latest_intelligence", new_callable=AsyncMock) as mock_brain:
        
        mock_get_user.return_value = User(telegram_id="12345", tier="starter", is_active=True) # Limit 5
        mock_brain.return_value = {
            "safe_bets": [{"selection": "Team A", "suggested_stake": 50}], # 5% of 1000
            "bankroll": 1000
        }
        mock_context.args = ["2000"]
        
        await bankroll(mock_update, mock_context)
        
        mock_update.message.reply_html.assert_called()
        args, _ = mock_update.message.reply_html.call_args
        # 5% of 2000 is 100
        assert "100.00" in args[0]

@pytest.mark.asyncio
async def test_rate_limit(mock_update, mock_context):
    """Verify users are rate limited."""
    with patch("automation.telegram_bot.get_or_create_user", new_callable=AsyncMock) as mock_get_user, \
         patch("automation.telegram_bot._rate_limits", {}) as mock_limits:
        
        mock_get_user.return_value = User(telegram_id="12345", tier="free", is_active=True)
        
        # 1st call
        await start(mock_update, mock_context)
        assert mock_update.message.reply_text.call_count == 1
        
        # 2nd call (immediate)
        await start(mock_update, mock_context)
        # Should NOT increment, but send rate limit msg
        mock_update.message.reply_text.assert_called_with("Slow down — one command every 10 seconds.")
