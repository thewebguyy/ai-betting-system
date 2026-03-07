"""
automation/notifications.py
Telegram bot + (optionally SendGrid email) alert system.
"""

import asyncio
from loguru import logger
from backend.config import get_settings

settings = get_settings()


async def send_telegram_message(text: str) -> bool:
    """Send a Telegram message to the configured chat."""
    if not settings.telegram_bot_token or not settings.telegram_chat_id:
        logger.warning("Telegram not configured; skipping alert.")
        return False

    try:
        from telegram import Bot
        bot = Bot(token=settings.telegram_bot_token)
        async with bot:
            await bot.send_message(
                chat_id=settings.telegram_chat_id,
                text=text,
                parse_mode="Markdown",
            )
        logger.info(f"Telegram alert sent: {text[:80]}…")
        return True
    except Exception as e:
        logger.error(f"Telegram send failed: {e}")
        return False


async def send_value_bet_alert(value_bet: dict, match_info: dict) -> None:
    """Format and send a value bet Telegram alert."""
    ev_pct = value_bet.get("ev", 0) * 100
    msg = (
        f"🎯 *Value Bet Alert*\n\n"
        f"🏟 Match: {match_info.get('home_team', '?')} vs {match_info.get('away_team', '?')}\n"
        f"📅 Date: {match_info.get('match_date', '?')}\n"
        f"🏦 Book: {value_bet.get('bookmaker', '?')}\n"
        f"✅ Selection: *{value_bet.get('selection', '?')}*\n"
        f"💰 Odds: {value_bet.get('decimal_odds', '?')}\n"
        f"📊 Model Prob: {value_bet.get('model_prob', 0):.1%}\n"
        f"📈 Edge: {value_bet.get('edge', 0):.2%}\n"
        f"💵 EV: {ev_pct:.1f}%\n"
        f"💼 Kelly Stake: {value_bet.get('suggested_stake', 0):.2f}\n\n"
        f"_For personal use only. Bet responsibly._"
    )
    await send_telegram_message(msg)


async def send_daily_summary(analytics: dict) -> None:
    """Send end-of-day performance summary via Telegram."""
    msg = (
        f"📊 *Daily Betting Summary*\n\n"
        f"Total Bets: {analytics.get('total_bets', 0)}\n"
        f"Won: {analytics.get('won', 0)} | Lost: {analytics.get('lost', 0)}\n"
        f"Hit Rate: {analytics.get('hit_rate', 0):.1f}%\n"
        f"Profit/Loss: {analytics.get('total_profit', 0):+.2f}\n"
        f"ROI: {analytics.get('roi', 0):+.2f}%\n"
        f"Bankroll Total Staked: {analytics.get('total_staked', 0):.2f}"
    )
    await send_telegram_message(msg)


def send_email_report(subject: str, html_body: str) -> bool:
    """
    Send an email via SendGrid (100 free/day).
    Requires SENDGRID_API_KEY in .env.
    """
    if not settings.sendgrid_api_key:
        logger.warning("SendGrid not configured; skipping email.")
        return False

    try:
        import sendgrid
        from sendgrid.helpers.mail import Mail, To, From, Subject, HtmlContent

        sg = sendgrid.SendGridAPIClient(api_key=settings.sendgrid_api_key)
        message = Mail(
            from_email=settings.sendgrid_from_email,
            to_emails=settings.sendgrid_from_email,  # send to self
            subject=subject,
            html_content=html_body,
        )
        response = sg.send(message)
        logger.info(f"Email sent: status {response.status_code}")
        return response.status_code == 202
    except Exception as e:
        logger.error(f"SendGrid failed: {e}")
        return False
