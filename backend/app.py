"""
backend/app.py
Main FastAPI application — entrypoint for the AI Betting Intelligence System.
"""

import json
from contextlib import asynccontextmanager
from datetime import timedelta
from typing import List, Optional

from fastapi import (
    FastAPI, Depends, HTTPException, status,
    WebSocket, WebSocketDisconnect, BackgroundTasks,
    Query
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc
from loguru import logger

from backend.config import get_settings
from backend.database import get_db, init_db
from backend.auth import authenticate_user, create_access_token, get_current_user
from backend.models import (
    Match, OddsHistory, ValueBet, Bet, Bankroll, League, Team, Report
)
from backend.schemas import (
    LoginRequest, TokenResponse,
    MatchOut, OddsOut, OddsIn,
    ValueBetOut, BetIn, BetOut, BetSettleIn,
    BankrollSnapshot, BankrollIn,
    AnalyticsOut, EVCalcIn, EVCalcOut,
    ReportOut, WSEvent,
)
from backend.cache import cache_get, cache_set, make_cache_key

settings = get_settings()

# ── WebSocket connection manager ──────────────────────────────────────────────
class ConnectionManager:
    def __init__(self):
        self.active: list[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.active.append(ws)
        logger.info(f"WS client connected. Total: {len(self.active)}")

    def disconnect(self, ws: WebSocket):
        if ws in self.active:
            self.active.remove(ws)

    async def broadcast(self, event: WSEvent):
        payload = event.model_dump_json()
        dead = []
        for ws in self.active:
            try:
                await ws.send_text(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)


manager = ConnectionManager()


# ── Lifespan ──────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting AI Betting Intelligence System…")
    await init_db()
    # Start background scheduler
    from automation.workflows import start_scheduler
    scheduler = start_scheduler()
    yield
    scheduler.shutdown(wait=False)
    logger.info("Shutdown complete.")


# ── App factory ───────────────────────────────────────────────────────────────
app = FastAPI(
    title="AI Betting Intelligence System",
    description="Personal value-betting toolkit powered by ML and AI reasoning.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ═══════════════════════════════════════════════════════════════════════════════
# ─── Auth ─────────────────────────────────────────────────────────────────────
# ═══════════════════════════════════════════════════════════════════════════════
@app.post("/auth/token", response_model=TokenResponse, tags=["Auth"])
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    if not authenticate_user(form_data.username, form_data.password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect credentials")
    token = create_access_token({"sub": form_data.username}, timedelta(minutes=settings.jwt_expire_minutes))
    return TokenResponse(access_token=token)


# ═══════════════════════════════════════════════════════════════════════════════
# ─── Health ───────────────────────────────────────────────────────────────────
# ═══════════════════════════════════════════════════════════════════════════════
@app.get("/health", tags=["System"])
async def health():
    return {"status": "ok", "version": "1.0.0"}


# ═══════════════════════════════════════════════════════════════════════════════
# ─── Odds ─────────────────────────────────────────────────────────────────────
# ═══════════════════════════════════════════════════════════════════════════════
@app.get("/odds", response_model=List[OddsOut], tags=["Odds"])
async def get_odds(
    match_id: Optional[int] = None,
    bookmaker: Optional[str] = None,
    limit: int = Query(50, le=200),
    db: AsyncSession = Depends(get_db),
    _user: str = Depends(get_current_user),
):
    cache_key = make_cache_key("odds", str(match_id), str(bookmaker), str(limit))
    cached = await cache_get(cache_key)
    if cached:
        return cached

    stmt = select(OddsHistory).order_by(desc(OddsHistory.fetched_at)).limit(limit)
    if match_id:
        stmt = stmt.where(OddsHistory.match_id == match_id)
    if bookmaker:
        stmt = stmt.where(OddsHistory.bookmaker == bookmaker)
    result = await db.execute(stmt)
    rows = result.scalars().all()
    out = [OddsOut.model_validate(r) for r in rows]
    await cache_set(cache_key, [o.model_dump() for o in out], ttl=60)
    return out


@app.post("/odds", response_model=OddsOut, tags=["Odds"], status_code=201)
async def add_odds(
    payload: OddsIn,
    db: AsyncSession = Depends(get_db),
    _user: str = Depends(get_current_user),
):
    row = OddsHistory(**payload.model_dump())
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return OddsOut.model_validate(row)


@app.post("/odds/fetch-live", tags=["Odds"])
async def fetch_live_odds(
    background_tasks: BackgroundTasks,
    _user: str = Depends(get_current_user),
):
    """Trigger a live odds scrape in the background."""
    from scrapers.odds_scraper import scrape_all_bookmakers
    background_tasks.add_task(scrape_all_bookmakers)
    return {"status": "scraping started"}


# ═══════════════════════════════════════════════════════════════════════════════
# ─── Value Bets ───────────────────────────────────────────────────────────────
# ═══════════════════════════════════════════════════════════════════════════════
@app.get("/value-bets", response_model=List[ValueBetOut], tags=["Value Bets"])
async def get_value_bets(
    status_filter: Optional[str] = Query(None, alias="status"),
    min_ev: float = Query(0.0),
    limit: int = Query(50, le=200),
    db: AsyncSession = Depends(get_db),
    _user: str = Depends(get_current_user),
):
    stmt = select(ValueBet).where(ValueBet.ev >= min_ev).order_by(desc(ValueBet.ev)).limit(limit)
    if status_filter:
        stmt = stmt.where(ValueBet.status == status_filter)
    result = await db.execute(stmt)
    return [ValueBetOut.model_validate(r) for r in result.scalars().all()]


@app.post("/value-bets/scan", tags=["Value Bets"])
async def scan_value_bets(
    background_tasks: BackgroundTasks,
    _user: str = Depends(get_current_user),
):
    """Trigger model scan for value bets across all upcoming matches."""
    from models.value_model import detect_value_bets_for_upcoming
    background_tasks.add_task(detect_value_bets_for_upcoming)
    return {"status": "scan started"}


# ═══════════════════════════════════════════════════════════════════════════════
# ─── EV Calculator ────────────────────────────────────────────────────────────
# ═══════════════════════════════════════════════════════════════════════════════
@app.post("/analytics/ev-calc", response_model=EVCalcOut, tags=["Analytics"])
async def calc_ev(
    payload: EVCalcIn,
    _user: str = Depends(get_current_user),
):
    from models.value_model import calculate_ev_kelly
    result = calculate_ev_kelly(
        decimal_odds=payload.decimal_odds,
        model_prob=payload.model_prob,
        stake=payload.stake,
        bankroll=payload.bankroll,
        kelly_fraction=payload.kelly_fraction,
    )
    return EVCalcOut(**result)


# ═══════════════════════════════════════════════════════════════════════════════
# ─── Analytics ────────────────────────────────────────────────────────────────
# ═══════════════════════════════════════════════════════════════════════════════
@app.get("/analytics", response_model=AnalyticsOut, tags=["Analytics"])
async def get_analytics(
    db: AsyncSession = Depends(get_db),
    _user: str = Depends(get_current_user),
):
    from backend.analytics import compute_analytics
    return await compute_analytics(db)


@app.get("/analytics/line-movement", tags=["Analytics"])
async def line_movement(
    match_id: int,
    bookmaker: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    _user: str = Depends(get_current_user),
):
    from backend.analytics import compute_line_movement
    return await compute_line_movement(db, match_id, bookmaker)


# ═══════════════════════════════════════════════════════════════════════════════
# ─── Bankroll ─────────────────────────────────────────────────────────────────
# ═══════════════════════════════════════════════════════════════════════════════
@app.get("/bankroll", response_model=List[BankrollSnapshot], tags=["Bankroll"])
async def get_bankroll(
    limit: int = Query(30, le=200),
    db: AsyncSession = Depends(get_db),
    _user: str = Depends(get_current_user),
):
    result = await db.execute(
        select(Bankroll).order_by(desc(Bankroll.snapshot_at)).limit(limit)
    )
    return [BankrollSnapshot.model_validate(r) for r in result.scalars().all()]


@app.post("/bankroll", response_model=BankrollSnapshot, tags=["Bankroll"], status_code=201)
async def add_bankroll_snapshot(
    payload: BankrollIn,
    db: AsyncSession = Depends(get_db),
    _user: str = Depends(get_current_user),
):
    row = Bankroll(**payload.model_dump())
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return BankrollSnapshot.model_validate(row)


# ═══════════════════════════════════════════════════════════════════════════════
# ─── Bets ─────────────────────────────────────────════════════════════════════
# ═══════════════════════════════════════════════════════════════════════════════
@app.get("/bets", response_model=List[BetOut], tags=["Bets"])
async def get_bets(
    result_filter: Optional[str] = Query(None, alias="result"),
    limit: int = Query(50, le=500),
    db: AsyncSession = Depends(get_db),
    _user: str = Depends(get_current_user),
):
    stmt = select(Bet).order_by(desc(Bet.placed_at)).limit(limit)
    if result_filter:
        stmt = stmt.where(Bet.result == result_filter)
    res = await db.execute(stmt)
    return [BetOut.model_validate(r) for r in res.scalars().all()]


@app.post("/bets", response_model=BetOut, tags=["Bets"], status_code=201)
async def place_bet(
    payload: BetIn,
    db: AsyncSession = Depends(get_db),
    _user: str = Depends(get_current_user),
):
    row = Bet(
        **payload.model_dump(),
        potential_payout=round(payload.stake * payload.decimal_odds, 2),
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return BetOut.model_validate(row)


@app.patch("/bets/{bet_id}/settle", response_model=BetOut, tags=["Bets"])
async def settle_bet(
    bet_id: int,
    payload: BetSettleIn,
    db: AsyncSession = Depends(get_db),
    _user: str = Depends(get_current_user),
):
    from datetime import datetime
    result = await db.execute(select(Bet).where(Bet.id == bet_id))
    bet = result.scalar_one_or_none()
    if not bet:
        raise HTTPException(status_code=404, detail="Bet not found")
    bet.result = payload.result
    bet.actual_payout = payload.actual_payout
    bet.settled_at = datetime.utcnow()
    await db.commit()
    await db.refresh(bet)
    return BetOut.model_validate(bet)


# ═══════════════════════════════════════════════════════════════════════════════
# ─── Matches ──────────────────────────────────────────────────────────────────
# ═══════════════════════════════════════════════════════════════════════════════
@app.get("/matches", response_model=List[MatchOut], tags=["Matches"])
async def get_matches(
    status_filter: Optional[str] = Query(None, alias="status"),
    limit: int = Query(20, le=100),
    db: AsyncSession = Depends(get_db),
    _user: str = Depends(get_current_user),
):
    stmt = select(Match).order_by(desc(Match.match_date)).limit(limit)
    if status_filter:
        stmt = stmt.where(Match.status == status_filter)
    res = await db.execute(stmt)
    return [MatchOut.model_validate(r) for r in res.scalars().all()]


# ═══════════════════════════════════════════════════════════════════════════════
# ─── Reports ──────────────────────────────────────────────────────────────────
# ═══════════════════════════════════════════════════════════════════════════════
@app.get("/reports", response_model=List[ReportOut], tags=["Reports"])
async def list_reports(
    db: AsyncSession = Depends(get_db),
    _user: str = Depends(get_current_user),
):
    res = await db.execute(select(Report).order_by(desc(Report.created_at)).limit(50))
    return [ReportOut.model_validate(r) for r in res.scalars().all()]


@app.post("/reports/generate", tags=["Reports"])
async def generate_report(
    report_type: str = Query("daily", enum=["daily", "match", "performance"]),
    match_id: Optional[int] = None,
    background_tasks: BackgroundTasks = BackgroundTasks(),
    _user: str = Depends(get_current_user),
):
    from automation.report_generator import generate_report_task
    background_tasks.add_task(generate_report_task, report_type, match_id)
    return {"status": f"{report_type} report generation started"}


# ═══════════════════════════════════════════════════════════════════════════════
# ─── WebSocket ────────────────────────────────────────────────────────────────
# ═══════════════════════════════════════════════════════════════════════════════
@app.websocket("/ws/alerts")
async def websocket_alerts(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            # Keep connection alive; messages are pushed by the system
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        manager.disconnect(websocket)


# ── make manager accessible to automation tasks ──────────────────────────────
app.state.ws_manager = manager
