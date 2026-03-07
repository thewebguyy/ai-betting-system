"""
models/value_model.py
Value bet detection engine.

Formulas:
  implied_prob   = 1 / decimal_odds
  true_implied   = implied_prob / sum_of_implied_probs  (vig removal)
  edge           = model_prob - true_implied
  ev             = (model_prob * (decimal_odds - 1)) - (1 - model_prob)
  kelly_fraction = (model_prob * (decimal_odds - 1) - (1 - model_prob)) / (decimal_odds - 1)
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Optional

from loguru import logger
from sqlalchemy import select

from backend.config import get_settings
from backend.database import AsyncSessionLocal
from backend.models import Match, OddsHistory, ValueBet, Bankroll
from models.prob_model import get_predictor, build_features, monte_carlo_probs

settings = get_settings()


# ═══════════════════════════════════════════════════════════════════════════════
# ─── Core Formula Functions ───────────────────────────────────────────────────
# ═══════════════════════════════════════════════════════════════════════════════

def implied_probability(decimal_odds: float) -> float:
    """Raw implied probability from decimal odds."""
    if decimal_odds <= 1.0:
        return 1.0
    return round(1 / decimal_odds, 6)


def remove_vig(home_odds: float, draw_odds: Optional[float], away_odds: float) -> dict:
    """
    Remove bookmaker's vig (overround) from 1X2 odds.
    Returns true probabilities without margin.
    """
    ip_home = implied_probability(home_odds)
    ip_away = implied_probability(away_odds)
    ip_draw = implied_probability(draw_odds) if draw_odds else 0.0

    total_ip = ip_home + ip_draw + ip_away  # this > 1 by the vig amount

    return {
        "home": round(ip_home / total_ip, 6),
        "draw": round(ip_draw / total_ip, 6) if draw_odds else 0.0,
        "away": round(ip_away / total_ip, 6),
        "overround": round(total_ip - 1, 6),
        "vig_pct": round((total_ip - 1) / total_ip * 100, 3),
    }


def expected_value(model_prob: float, decimal_odds: float) -> float:
    """
    EV per unit staked.
    ev = P(win) * profit + P(loss) * (-1)
       = model_prob * (decimal_odds - 1) - (1 - model_prob)
    """
    profit = decimal_odds - 1
    return round(model_prob * profit - (1 - model_prob), 6)


def kelly_criterion(model_prob: float, decimal_odds: float) -> float:
    """
    Full Kelly fraction of bankroll to bet.
    f* = (b*p - q) / b   where b = decimal_odds-1, p = model_prob, q = 1-model_prob
    f* < 0 means no bet.
    """
    b = decimal_odds - 1
    p = model_prob
    q = 1 - p
    if b <= 0:
        return 0.0
    f = (b * p - q) / b
    return round(max(f, 0.0), 6)


def calculate_ev_kelly(
    decimal_odds: float,
    model_prob: float,
    stake: float = 100.0,
    bankroll: float = 1000.0,
    kelly_fraction: float = 0.25,
) -> dict:
    """
    Full EV + Kelly calculation for the API /analytics/ev-calc endpoint.
    """
    ip = implied_probability(decimal_odds)
    edge = round(model_prob - ip, 6)
    ev = expected_value(model_prob, decimal_odds)
    kf_full = kelly_criterion(model_prob, decimal_odds)
    kf_frac = round(kf_full * kelly_fraction, 6)
    suggested_stake = round(bankroll * kf_frac, 2)

    return {
        "implied_prob": round(ip, 4),
        "edge": round(edge, 4),
        "ev": round(ev, 4),
        "ev_percent": round(ev * 100, 2),
        "kelly_full": round(kf_full, 4),
        "kelly_fractional": round(kf_frac, 4),
        "suggested_stake": suggested_stake,
        "is_value": edge >= settings.min_value_threshold and ev > 0,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# ─── Value Bet Detection Pipeline ─────────────────────────────────────────────
# ═══════════════════════════════════════════════════════════════════════════════

def detect_value_from_odds(
    home_elo: float, away_elo: float,
    home_form: Optional[str], away_form: Optional[str],
    home_injuries: int, away_injuries: int,
    home_odds: float, draw_odds: Optional[float], away_odds: float,
    bookmaker: str,
    match_id: Optional[int] = None,
    bankroll: float = 1000.0,
) -> list[dict]:
    """
    Given match context and odds from one bookmaker, return list of value bets
    (may contain 0-3 selections: Home/Draw/Away).
    """
    # Get model probabilities
    predictor = get_predictor()
    features = build_features(
        home_elo=home_elo, away_elo=away_elo,
        home_form=home_form, away_form=away_form,
        home_injuries_count=home_injuries,
        away_injuries_count=away_injuries,
    )
    model_h, model_d, model_a = predictor.predict_proba(features)

    # Vig-normalised implied probs
    vig = remove_vig(home_odds, draw_odds, away_odds)

    selections = [
        ("Home", home_odds, model_h, vig["home"]),
        ("Away", away_odds, model_a, vig["away"]),
    ]
    if draw_odds:
        selections.append(("Draw", draw_odds, model_d, vig["draw"]))

    value_bets = []
    for selection, d_odds, model_p, true_ip in selections:
        edge = model_p - true_ip
        ev = expected_value(model_p, d_odds)
        kf_full = kelly_criterion(model_p, d_odds)
        kf_frac = round(kf_full * settings.kelly_fraction, 6)
        stake = round(bankroll * kf_frac, 2)

        if edge >= settings.min_value_threshold and ev > 0:
            value_bets.append({
                "match_id": match_id,
                "bookmaker": bookmaker,
                "market": "1X2",
                "selection": selection,
                "decimal_odds": d_odds,
                "implied_prob": implied_probability(d_odds),
                "true_implied": true_ip,
                "model_prob": model_p,
                "edge": round(edge, 6),
                "ev": round(ev, 6),
                "kelly_fraction": kf_frac,
                "suggested_stake": stake,
            })

    return value_bets


async def detect_value_bets_for_upcoming():
    """
    Background task: scan all upcoming matches and their latest odds,
    run the model, store any value bets found, and send alerts.
    """
    logger.info("Starting value bet scan…")
    detected_count = 0

    async with AsyncSessionLocal() as db:
        # Get current bankroll
        br_result = await db.execute(
            select(Bankroll).order_by(Bankroll.snapshot_at.desc()).limit(1)
        )
        br = br_result.scalar_one_or_none()
        bankroll = br.balance if br else settings.default_bankroll

        # Get upcoming matches
        matches_result = await db.execute(
            select(Match).where(Match.status == "scheduled")
        )
        matches = matches_result.scalars().all()

        for match in matches:
            # Get latest odds per bookmaker
            odds_result = await db.execute(
                select(OddsHistory)
                .where(OddsHistory.match_id == match.id)
                .order_by(OddsHistory.fetched_at.desc())
                .limit(10)  # up to 10 bookmakers
            )
            odds_rows = odds_result.scalars().all()

            seen_bookmakers: set[str] = set()
            for odds in odds_rows:
                if odds.bookmaker in seen_bookmakers:
                    continue
                seen_bookmakers.add(odds.bookmaker)

                if not odds.home_odds or not odds.away_odds:
                    continue

                vbs = detect_value_from_odds(
                    home_elo=match.model_home_prob or 1500.0,  # fallback ELO
                    away_elo=match.model_away_prob or 1500.0,
                    home_form=match.home_form,
                    away_form=match.away_form,
                    home_injuries=len((match.home_injuries or "").split(",")) if match.home_injuries else 0,
                    away_injuries=len((match.away_injuries or "").split(",")) if match.away_injuries else 0,
                    home_odds=odds.home_odds,
                    draw_odds=odds.draw_odds,
                    away_odds=odds.away_odds,
                    bookmaker=odds.bookmaker,
                    match_id=match.id,
                    bankroll=bankroll,
                )

                for vb in vbs:
                    row = ValueBet(**vb)
                    db.add(row)
                    detected_count += 1
                    logger.info(
                        f"Value bet: {vb['selection']} @ {vb['decimal_odds']} "
                        f"EV={vb['ev']:.3f} Edge={vb['edge']:.3f} (Book: {vb['bookmaker']})"
                    )

        await db.commit()

    logger.info(f"Value bet scan complete. Found {detected_count} value bets.")

    # Fire Telegram/WS alerts (non-blocking)
    if detected_count > 0:
        try:
            from automation.notifications import send_telegram_message
            await send_telegram_message(f"🎯 {detected_count} new value bets detected! Check the dashboard.")
        except Exception as e:
            logger.warning(f"Alert send failed: {e}")

    return detected_count
