"""
backend/models.py
SQLAlchemy ORM models matching db/schema.sql
"""

from datetime import datetime
from typing import Optional
from sqlalchemy import (
    Integer, Float, Text, DateTime, ForeignKey, String, Boolean
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from backend.database import Base


class League(Base):
    __tablename__ = "leagues"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    api_id: Mapped[Optional[str]] = mapped_column(Text, unique=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    country: Mapped[Optional[str]] = mapped_column(Text)
    sport: Mapped[str] = mapped_column(Text, default="football")
    season: Mapped[Optional[str]] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    matches: Mapped[list["Match"]] = relationship("Match", back_populates="league")


class Team(Base):
    __tablename__ = "teams"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    api_id: Mapped[Optional[str]] = mapped_column(Text, unique=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    short_name: Mapped[Optional[str]] = mapped_column(Text)
    country: Mapped[Optional[str]] = mapped_column(Text)
    league_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("leagues.id"))
    elo_rating: Mapped[float] = mapped_column(Float, default=1500.0)
    attack_strength: Mapped[float] = mapped_column(Float, default=1.0)
    defence_strength: Mapped[float] = mapped_column(Float, default=1.0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)



class Match(Base):
    __tablename__ = "matches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    api_id: Mapped[Optional[str]] = mapped_column(Text, unique=True)
    league_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("leagues.id"))
    home_team_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("teams.id"))
    away_team_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("teams.id"))
    match_date: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    status: Mapped[str] = mapped_column(Text, default="scheduled")
    home_score: Mapped[Optional[int]] = mapped_column(Integer)
    away_score: Mapped[Optional[int]] = mapped_column(Integer)
    home_form: Mapped[Optional[str]] = mapped_column(Text)
    away_form: Mapped[Optional[str]] = mapped_column(Text)
    home_injuries: Mapped[Optional[str]] = mapped_column(Text)
    away_injuries: Mapped[Optional[str]] = mapped_column(Text)
    weather: Mapped[Optional[str]] = mapped_column(Text)
    venue: Mapped[Optional[str]] = mapped_column(Text)
    model_home_prob: Mapped[Optional[float]] = mapped_column(Float)
    model_draw_prob: Mapped[Optional[float]] = mapped_column(Float)
    model_away_prob: Mapped[Optional[float]] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    league: Mapped[Optional["League"]] = relationship("League", back_populates="matches")
    home_team: Mapped[Optional["Team"]] = relationship("Team", foreign_keys=[home_team_id])
    away_team: Mapped[Optional["Team"]] = relationship("Team", foreign_keys=[away_team_id])
    odds: Mapped[list["OddsHistory"]] = relationship("OddsHistory", back_populates="match", cascade="all, delete-orphan")
    value_bets: Mapped[list["ValueBet"]] = relationship("ValueBet", back_populates="match")



class OddsHistory(Base):
    __tablename__ = "odds_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    match_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("matches.id", ondelete="CASCADE"))
    bookmaker: Mapped[str] = mapped_column(Text, nullable=False)
    market: Mapped[str] = mapped_column(Text, default="1X2")
    home_odds: Mapped[Optional[float]] = mapped_column(Float)
    draw_odds: Mapped[Optional[float]] = mapped_column(Float)
    away_odds: Mapped[Optional[float]] = mapped_column(Float)
    over_odds: Mapped[Optional[float]] = mapped_column(Float)
    under_odds: Mapped[Optional[float]] = mapped_column(Float)
    line: Mapped[Optional[float]] = mapped_column(Float)
    fetched_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    match: Mapped[Optional["Match"]] = relationship("Match", back_populates="odds")


class ValueBet(Base):
    __tablename__ = "value_bets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    match_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("matches.id"))
    bookmaker: Mapped[str] = mapped_column(Text, nullable=False)
    market: Mapped[str] = mapped_column(Text, nullable=False)
    selection: Mapped[str] = mapped_column(Text, nullable=False)
    decimal_odds: Mapped[float] = mapped_column(Float, nullable=False)
    implied_prob: Mapped[float] = mapped_column(Float, nullable=False)
    true_implied: Mapped[float] = mapped_column(Float, nullable=False)
    model_prob: Mapped[float] = mapped_column(Float, nullable=False)
    edge: Mapped[float] = mapped_column(Float, nullable=False)
    ev: Mapped[float] = mapped_column(Float, nullable=False)
    kelly_fraction: Mapped[float] = mapped_column(Float, nullable=False)
    suggested_stake: Mapped[Optional[float]] = mapped_column(Float)
    status: Mapped[str] = mapped_column(Text, default="pending")
    detected_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    match: Mapped[Optional["Match"]] = relationship("Match", back_populates="value_bets")


class Bet(Base):
    __tablename__ = "bets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    value_bet_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("value_bets.id"))
    match_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("matches.id"))
    bookmaker: Mapped[str] = mapped_column(Text, nullable=False)
    market: Mapped[str] = mapped_column(Text, nullable=False)
    selection: Mapped[str] = mapped_column(Text, nullable=False)
    decimal_odds: Mapped[float] = mapped_column(Float, nullable=False)
    stake: Mapped[float] = mapped_column(Float, nullable=False)
    potential_payout: Mapped[float] = mapped_column(Float, nullable=False)
    actual_payout: Mapped[float] = mapped_column(Float, default=0.0)
    result: Mapped[str] = mapped_column(Text, default="pending")
    placed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    settled_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    notes: Mapped[Optional[str]] = mapped_column(Text)
    closing_odds: Mapped[Optional[float]] = mapped_column(Float)
    clv: Mapped[Optional[float]] = mapped_column(Float)

    match: Mapped[Optional["Match"]] = relationship("Match")





class Bankroll(Base):
    __tablename__ = "bankroll"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    balance: Mapped[float] = mapped_column(Float, nullable=False)
    note: Mapped[Optional[str]] = mapped_column(Text)
    snapshot_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class AICache(Base):
    __tablename__ = "ai_cache"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    cache_key: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    prompt_hash: Mapped[str] = mapped_column(Text, nullable=False)
    response: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime)


class Report(Base):
    __tablename__ = "reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    report_type: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    file_path: Mapped[Optional[str]] = mapped_column(Text)
    content_md: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class TeamMatchStats(Base):
    __tablename__ = "team_match_stats"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    match_id: Mapped[int] = mapped_column(Integer, ForeignKey("matches.id", ondelete="CASCADE"))
    team_id: Mapped[int] = mapped_column(Integer, ForeignKey("teams.id", ondelete="CASCADE"))
    xg_for: Mapped[float] = mapped_column(Float, default=0.0)
    xg_against: Mapped[float] = mapped_column(Float, default=0.0)
    goals_for: Mapped[int] = mapped_column(Integer, default=0)
    goals_against: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class SystemConfig(Base):
    __tablename__ = "system_config"

    key: Mapped[str] = mapped_column(Text, primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


