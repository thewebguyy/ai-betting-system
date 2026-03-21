"""
backend/schemas.py
Pydantic v2 schemas for API request/response validation.
"""

from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field, ConfigDict


# ─── Auth ─────────────────────────────────────────────────────────────────────
class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


# ─── League ───────────────────────────────────────────────────────────────────
class LeagueOut(BaseModel):
    model_config = ConfigDict(from_attributes=True, protected_namespaces=())

    id: int
    api_id: Optional[str]
    name: str
    country: Optional[str]
    sport: str
    season: Optional[str]


# ─── Match ────────────────────────────────────────────────────────────────────
class MatchOut(BaseModel):
    model_config = ConfigDict(from_attributes=True, protected_namespaces=())

    id: int
    api_id: Optional[str]
    league_id: Optional[int]
    home_team_id: Optional[int]
    away_team_id: Optional[int]
    match_date: datetime
    status: str
    home_score: Optional[int]
    away_score: Optional[int]
    model_home_prob: Optional[float]
    model_draw_prob: Optional[float]
    model_away_prob: Optional[float]


# ─── Odds ─────────────────────────────────────────────────────────────────────
class OddsOut(BaseModel):
    model_config = ConfigDict(from_attributes=True, protected_namespaces=())

    id: int
    match_id: Optional[int]
    bookmaker: str
    market: str
    home_odds: Optional[float]
    draw_odds: Optional[float]
    away_odds: Optional[float]
    fetched_at: datetime


class OddsIn(BaseModel):
    match_id: int
    bookmaker: str
    market: str = "1X2"
    home_odds: Optional[float] = None
    draw_odds: Optional[float] = None
    away_odds: Optional[float] = None
    over_odds: Optional[float] = None
    under_odds: Optional[float] = None
    line: Optional[float] = None


# ─── Value Bets ───────────────────────────────────────────────────────────────
class ValueBetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True, protected_namespaces=())

    id: int
    match_id: Optional[int]
    bookmaker: str
    market: str
    selection: str
    decimal_odds: float
    implied_prob: float
    true_implied: float
    model_prob: float
    edge: float
    ev: float
    kelly_fraction: float
    suggested_stake: Optional[float]
    status: str
    detected_at: datetime


# ─── Bets ─────────────────────────────────────────────────────────────────────
class BetIn(BaseModel):
    value_bet_id: Optional[int] = None
    match_id: Optional[int] = None
    bookmaker: str
    market: str
    selection: str
    decimal_odds: float = Field(gt=1.0)
    stake: float = Field(gt=0)
    notes: Optional[str] = None


class BetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True, protected_namespaces=())

    id: int
    bookmaker: str
    market: str
    selection: str
    decimal_odds: float
    stake: float
    potential_payout: float
    actual_payout: float
    result: str
    placed_at: datetime
    settled_at: Optional[datetime]
    notes: Optional[str]
    closing_odds: Optional[float]
    clv: Optional[float]



class BetSettleIn(BaseModel):
    result: str  # won|lost|void|push
    actual_payout: float = 0.0


# ─── Bankroll ─────────────────────────────────────────────────────────────────
class BankrollSnapshot(BaseModel):
    model_config = ConfigDict(from_attributes=True, protected_namespaces=())

    id: int
    balance: float
    note: Optional[str]
    snapshot_at: datetime


class BankrollIn(BaseModel):
    balance: float = Field(gt=0)
    note: Optional[str] = None


# ─── Analytics ────────────────────────────────────────────────────────────────
class AnalyticsOut(BaseModel):
    total_bets: int
    won: int
    lost: int
    void: int
    total_staked: float
    total_profit: float
    roi: float
    yield_pct: float
    hit_rate: float
    avg_odds: float
    pending: int
    avg_clv: float = 0.0
    roi_by_league: dict = {}
    roi_by_market: dict = {}
    roi_by_bookmaker: dict = {}
    calibration_data: list = []  # List of {bucket: "50-55", actual_win_rate: 0.52, count: 10}



# ─── EV Calculator ────────────────────────────────────────────────────────────
class EVCalcIn(BaseModel):
    decimal_odds: float = Field(gt=1.0)
    model_prob: float = Field(ge=0.0, le=1.0)
    stake: float = Field(default=100.0, gt=0)
    bankroll: float = Field(default=1000.0, gt=0)
    kelly_fraction: float = Field(default=0.25, ge=0.01, le=1.0)


class EVCalcOut(BaseModel):
    implied_prob: float
    edge: float
    ev: float
    ev_percent: float
    kelly_full: float
    kelly_fractional: float
    suggested_stake: float
    is_value: bool


# ─── Reports ──────────────────────────────────────────────────────────────────
class ReportOut(BaseModel):
    model_config = ConfigDict(from_attributes=True, protected_namespaces=())

    id: int
    report_type: str
    title: str
    file_path: Optional[str]
    created_at: datetime


# ─── WebSocket event ──────────────────────────────────────────────────────────
class WSEvent(BaseModel):
    event_type: str   # value_bet|line_move|alert
    data: dict
    timestamp: datetime = Field(default_factory=datetime.utcnow)


# ─── Bot & Users (Phase 5) ───────────────────────────────────────────────────
class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    telegram_id: str
    username: Optional[str]
    tier: str
    is_active: bool
    registered_at: datetime
    last_seen_at: Optional[datetime]


class UserUpdate(BaseModel):
    tier: Optional[str] = None
    is_active: Optional[bool] = None


class BotStatus(BaseModel):
    is_running: bool
    commands_processed: int
    last_heartbeat: datetime
