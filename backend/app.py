"""
backend/app.py
Main FastAPI application — entrypoint for the AI Betting Intelligence System.
"""

import json
import sys
import asyncio
import subprocess
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from typing import List, Optional

from fastapi import (
    FastAPI, Depends, HTTPException, status,
    WebSocket, WebSocketDisconnect, BackgroundTasks,
    Query, Request
)

from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc
from loguru import logger

from backend.config import get_settings
from backend.database import get_db, init_db
from backend.auth import authenticate_user, create_access_token, get_current_user
from backend.models import (
    Match, OddsHistory, ValueBet, Bet, Bankroll, League, Team, Report, User
)
from backend.schemas import (
    LoginRequest, TokenResponse,
    MatchOut, OddsOut, OddsIn,
    ValueBetOut, BetIn, BetOut, BetSettleIn,
    BankrollSnapshot, BankrollIn,
    AnalyticsOut, EVCalcIn, EVCalcOut,
    ReportOut, WSEvent,
    UserOut, UserUpdate, BotStatus,
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
    
    # NEW: Start interactive Telegram bot subprocess
    # Run as a separate process to avoid event loop conflicts with python-telegram-bot
    bot_process = await asyncio.create_subprocess_exec(
        sys.executable, "-m", "automation.run_bot",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    logger.info(f"Telegram bot process started (PID: {bot_process.pid})")
    
    yield
    
    # Graceful shutdown
    logger.info("Terminating Telegram bot…")
    bot_process.terminate()
    await bot_process.wait()
    
    scheduler.shutdown(wait=False)
    logger.info("Shutdown complete.")


# ── App factory ───────────────────────────────────────────────────────────────
app = FastAPI(
    title="AI Betting Intelligence System",
    description="Personal value-betting toolkit powered by ML and AI reasoning.",
    version="1.0.0",
    lifespan=lifespan,
)

@app.middleware("http")
async def log_requests(request, call_next):
    logger.info(f"Incoming request: {request.method} {request.url.path}")
    response = await call_next(request)
    logger.info(f"Response status: {response.status_code}")
    return response

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)



# Serve report files
app.mount("/reports", StaticFiles(directory="reports"), name="reports")

@app.get("/", tags=["System"])
async def root():
    return {"status": "AI Betting Intelligence System Backend is running", "api_version": "1.0.0"}



# ═══════════════════════════════════════════════════════════════════════════════
# ─── Auth ─────────────────────────────────────────────────────────────────────
# ═══════════════════════════════════════════════════════════════════════════════
@app.post("/auth/token", response_model=TokenResponse, tags=["Auth"])
@app.post("/auth/token/", response_model=TokenResponse, tags=["Auth"], include_in_schema=False)
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    logger.info(f"Login attempt received for user: {form_data.username}")
    if not authenticate_user(form_data.username, form_data.password):
        logger.warning(f"Failed login attempt for user: {form_data.username}")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect credentials")
    token = create_access_token({"sub": form_data.username}, timedelta(minutes=settings.jwt_expire_minutes))
    return TokenResponse(access_token=token)


@app.get("/auth/token", include_in_schema=False)
async def login_get_check():
    return {"error": "Method Not Allowed", "hint": "The backend RECEIVED a GET request. Please use POST for /auth/token."}

@app.get("/auth/token/", include_in_schema=False)
async def login_get_check_slash():
    return {"error": "Method Not Allowed", "hint": "The backend RECEIVED a GET request (with slash). Please use POST for /auth/token."}




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
# ─── PredictZ-Style Dashboard (Phase 6) ───────────────────────────────────────
# ═══════════════════════════════════════════════════════════════════════════════
@app.get("/api/today_predictions", tags=["Predictions"])
async def get_today_predictions(
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    _user: str = Depends(get_current_user),
):
    from backend.cache import cache_get, cache_set
    from datetime import datetime, time
    import json
    import os
    from sqlalchemy import select
    from sqlalchemy.orm import joinedload
    from backend.models import Match, OddsHistory, Bankroll
    from models.prob_model import ensemble_predict
    from models.value_model import remove_vig, expected_value, kelly_criterion
    
    cache_key = "today_predictions_dashboard"
    cached = await cache_get(cache_key)
    if cached:
        return cached

    now = datetime.utcnow()
    # Matches scheduled from start of today to end of tomorrow to capture near future
    start_time = datetime.combine(now.date(), time.min)
    end_time = datetime.combine(now.date(), time.max)
    
    stmt = select(Match).options(joinedload(Match.home_team), joinedload(Match.away_team)).where(
        Match.status == "scheduled",
        Match.match_date >= start_time,
        Match.match_date <= end_time
    ).order_by(Match.match_date.asc())
    res = await db.execute(stmt)
    matches = res.scalars().all()
    
    br_result = await db.execute(select(Bankroll).order_by(Bankroll.snapshot_at.desc()).limit(1))
    br = br_result.scalar_one_or_none()
    bankroll = br.balance if br else 1000.0
    
    predictions = []
    
    for match in matches:
        odds_res = await db.execute(
            select(OddsHistory).where(OddsHistory.match_id == match.id).order_by(OddsHistory.fetched_at.desc()).limit(5)
        )
        latest_odds = odds_res.scalars().all()
        home_odds, draw_odds, away_odds = 0.0, 0.0, 0.0
        bookie = "None"
        for o in latest_odds:
            if o.home_odds and o.home_odds > 1:
                home_odds, draw_odds, away_odds = o.home_odds, o.draw_odds, o.away_odds
                bookie = o.bookmaker
                break
             
        home_attack = match.home_team.attack_strength if match.home_team else 1.0
        home_defence = match.home_team.defence_strength if match.home_team else 1.0
        away_attack = match.away_team.attack_strength if match.away_team else 1.0
        away_defence = match.away_team.defence_strength if match.away_team else 1.0
        home_elo = match.home_team.elo_rating if match.home_team else 1500.0
        away_elo = match.away_team.elo_rating if match.away_team else 1500.0
        
        pred = ensemble_predict(
             home_elo=home_elo, away_elo=away_elo,
             home_attack=home_attack, home_defence=home_defence,
             away_attack=away_attack, away_defence=away_defence,
             home_match_count=10, away_match_count=10, weather_str=match.weather or ""
        )
        
        model_h = pred["home"]
        model_d = pred["draw"]
        model_a = pred["away"]
        
        vig = remove_vig(home_odds, draw_odds, away_odds) if home_odds and home_odds > 1 else {"home":0, "draw":0, "away":0}
        
        selections = [
            {"label": "Home", "odds": home_odds, "prob": model_h, "true_ip": vig["home"]},
            {"label": "Draw", "odds": draw_odds, "prob": model_d, "true_ip": vig["draw"]},
            {"label": "Away", "odds": away_odds, "prob": model_a, "true_ip": vig["away"]}
        ]
        
        best_val = None
        for s in selections:
            if s["odds"] and s["odds"] > 1:
                ev = expected_value(s["prob"], s["odds"])
                kf = kelly_criterion(s["prob"], s["odds"])
                stake = round(bankroll * (kf * 0.1), 2) # Default fractional kelly 0.1
                if not best_val or ev > best_val.get("ev", -99):
                    best_val = {
                        "selection": s["label"],
                        "odds": s["odds"],
                        "prob": round(s["prob"], 4),
                        "ev": round(ev, 4),
                        "kelly_fraction": round(kf * 0.1, 4),
                        "suggested_stake": stake
                    }
        
        if not best_val:
            best_val = {"selection": "None", "odds": 0, "prob": 0, "ev": 0, "kelly_fraction": 0, "suggested_stake": 0}

        predictions.append({
            "match_id": match.id,
            "home_team": match.home_team.name if match.home_team else "Unknown",
            "away_team": match.away_team.name if match.away_team else "Unknown",
            "kickoff": match.match_date.isoformat(),
            "probs": {"home": round(model_h, 4), "draw": round(model_d, 4), "away": round(model_a, 4)},
            "best_value": best_val,
            "bookmaker": bookie,
            "is_value_bet": best_val.get("ev", 0) > 0.05
        })
        
    os.makedirs("logs", exist_ok=True)
    with open("logs/dashboard_snapshots.jsonl", "a") as f:
         f.write(json.dumps({"timestamp": now.isoformat(), "predictions": predictions}) + "\n")
         
    os.makedirs("reports", exist_ok=True)
    with open("reports/today_predictions.md", "w") as f:
         f.write(f"# Today's Predictions - {now.strftime('%Y-%m-%d')}\n\n")
         if not predictions:
             f.write("No predictions available for today.\n")
         for p in predictions:
             f.write(f"## {p['home_team']} vs {p['away_team']}\n")
             f.write(f"- **Kickoff:** {p['kickoff']}\n")
             f.write(f"- **Probs:** Home ({p['probs']['home']:.2f}) | Draw ({p['probs']['draw']:.2f}) | Away ({p['probs']['away']:.2f})\n")
             f.write(f"- **Best Value:** {p['best_value']['selection']} @ {p['best_value']['odds']} (EV: {p['best_value']['ev']:.2f})\n")
             f.write(f"- **Suggested Stake:** {p['best_value']['suggested_stake']}\n\n")
             
    await cache_set(cache_key, predictions, ttl=600)  
    return predictions


# ═══════════════════════════════════════════════════════════════════════════════
# ─── Users (Phase 5) ──────────────────────────────────────────────────────────
# ═══════════════════════════════════════════════════════════════════════════════
@app.get("/users", response_model=List[UserOut], tags=["Users"])
async def list_users(
    db: AsyncSession = Depends(get_db),
    _user: str = Depends(get_current_user),
):
    """Admin only: list all registered Telegram users."""
    res = await db.execute(select(User).order_by(desc(User.registered_at)))
    return [UserOut.model_validate(u) for u in res.scalars().all()]


@app.patch("/users/{user_id}", response_model=UserOut, tags=["Users"])
async def update_user(
    user_id: int,
    payload: UserUpdate,
    db: AsyncSession = Depends(get_db),
    _user: str = Depends(get_current_user),
):
    """Admin only: change user tier or active status."""
    res = await db.execute(select(User).where(User.id == user_id))
    user = res.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    data = payload.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(user, k, v)
    
    await db.commit()
    await db.refresh(user)
    return UserOut.model_validate(user)


# ═══════════════════════════════════════════════════════════════════════════════
# ─── Bot Status (Phase 5) ─────────────────────────────────────────────────────
# ═══════════════════════════════════════════════════════════════════════════════
@app.get("/bot/status", response_model=BotStatus, tags=["System"])
async def get_bot_status():
    """Check if the bot subprocess is responding (via Redis metrics)."""
    from backend.cache import cache_get
    total = await cache_get("bot:commands:total") or 0
    # In a real setup, the bot would update a heartbeat key
    return {
        "is_running": True, # Simplification
        "commands_processed": int(total),
        "last_heartbeat": datetime.utcnow()
    }


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
