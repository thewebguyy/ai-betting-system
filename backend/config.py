"""
backend/config.py
Centralised configuration loaded from .env via pydantic-settings.
"""

from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ─── App ──────────────────────────────────────────────────────────────────
    app_env: str = "development"
    app_secret_key: str = "changeme"
    app_host: str = "0.0.0.0"
    app_port: int = 8000

    # ─── JWT ──────────────────────────────────────────────────────────────────
    jwt_secret: str = "changeme-jwt"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 10080
    admin_username: str = "admin"
    admin_password: str = "changeme"

    # ─── DB ───────────────────────────────────────────────────────────────────
    database_url: str = "sqlite+aiosqlite:///./db/betting.db"

    # ─── Redis ────────────────────────────────────────────────────────────────
    redis_url: str = "redis://localhost:6379/0"
    cache_ttl_seconds: int = 300

    # ─── Sports APIs ──────────────────────────────────────────────────────────
    api_football_key: str = ""
    odds_api_key: str = ""
    thesportsdb_api_key: str = "2"
    balldontlie_api_key: str = ""

    # ─── AI Providers ─────────────────────────────────────────────────────────
    gemini_api_key: str = ""
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com/v1"
    deepseek_api_key: str = ""

    # ─── Telegram ─────────────────────────────────────────────────────────────
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    # ─── SendGrid ─────────────────────────────────────────────────────────────
    sendgrid_api_key: str = ""
    sendgrid_from_email: str = "alerts@example.com"

    # ─── Betting Strategy ─────────────────────────────────────────────────────
    default_bankroll: float = 1000.0
    kelly_fraction: float = 0.25
    min_ev_threshold: float = 0.05
    min_value_threshold: float = 0.05
    odds_line_move_alert: float = 0.10
    default_vig_margin: float = 0.05


@lru_cache
def get_settings() -> Settings:
    return Settings()
