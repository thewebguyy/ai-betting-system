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
from sqlalchemy.orm import joinedload

from backend.config import get_settings
from backend.database import AsyncSessionLocal
from backend.models import Match, OddsHistory, ValueBet, Bankroll
from models.prob_model import get_predictor, build_features, ensemble_predict

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


def calculate_intelligence_score(
    ev: float,
    match_count: int,
    overround: float,
    risks_found: bool = False
) -> float:
    """
    Intelligence Score = (EV * 0.4) + (Data Depth * 0.3) + (Vig-Adjustment * 0.2) + (News-Factor * 0.1)
    Normalized to 0.0 - 1.0 range.
    """
    # EV usually -1.0 to 2.0. Scale to 0-1 for scoring.
    ev_score = min(1.0, max(0.0, ev * 5.0)) # 0.2 EV = 100% score for this component
    
    # Data Depth: Higher is better. Scales to 1.0 at 30+ matches of history.
    # Replaces 'Monte Carlo CI' which gave false precision.
    data_score = min(1.0, max(0.0, match_count / 30.0))
    
    # Vig-Adjustment: Lower overround is better.
    # Typical overround 0.03 to 0.15.
    vig_score = max(0.0, 1.0 - (overround * 5.0)) # 0.20 overround = 0 score
    
    # News-Factor
    news_score = 0.5 if risks_found else 1.0
    
    score = (ev_score * 0.4) + (data_score * 0.3) + (vig_score * 0.2) + (news_score * 0.1)
    return round(score, 4)


def dynamic_kelly(ev: float, confidence: float, consecutive_losses: int, market: str, multiplier: float) -> float:
    """
    Phase 4: Dynamic Kelly calculation with decay for consecutive losses.
    """
    # Base fraction derived from EV and confidence
    f = ev * confidence
    
    # Apply decay for consecutive losses (10% reduction per loss)
    decay = 0.9 ** consecutive_losses
    f *= decay
    
    # Market-based safety factor
    if market == "correct_score":
        f *= 0.4  # Correct score is high variance, reduce stake further
        
    # Final adjustment using the passed multiplier
    f *= (1 + multiplier)
    
    return round(f, 4)


# ═══════════════════════════════════════════════════════════════════════════════
# ─── Value Bet Detection Pipeline ─────────────────────────────────────────────
# ═══════════════════════════════════════════════════════════════════════════════

def detect_value_from_odds(
    home_attack: float, home_defence: float,
    away_attack: float, away_defence: float,
    home_odds: float, draw_odds: Optional[float], away_odds: float,
    home_elo: float = 1500.0,
    away_elo: float = 1500.0,
    home_match_count: int = 0,
    away_match_count: int = 0,
    weather_str: str = "",
    bookmaker: str = "bet365",
    match_id: Optional[int] = None,
    bankroll: float = 1000.0,
    kelly_fraction: float = 0.1, # Default to 1/10th for safety per critique
) -> tuple[list[dict], tuple[float, float, float]]:

    """
    Given match context (team strengths, weather) and odds from one bookmaker,
    return list of value bets (may contain 0-3 selections: Home/Draw/Away).
    """
    # Get ensemble predictions
    pred = ensemble_predict(
        home_elo=home_elo,
        away_elo=away_elo,
        home_attack=home_attack, home_defence=home_defence,
        away_attack=away_attack, away_defence=away_defence,
        home_match_count=home_match_count,
        away_match_count=away_match_count,
        weather_str=weather_str
    )
    
    # CRITICAL: If data is insufficient, we do NOT generate value bets
    if not pred.get("is_sufficient", False):
        return [], (pred["home"], pred["draw"], pred["away"])

    model_h, model_d, model_a = pred["home"], pred["draw"], pred["away"]
    confidence = pred["confidence"]



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
        kf_frac = round(kf_full * kelly_fraction, 6)

        stake = round(bankroll * kf_frac, 2)

        if edge >= settings.min_value_threshold and ev > 0:
            # Calculate intelligence score
            # Risks are found if weather is extreme or injuries are flagged (to be enhanced)
            risks = "extreme" in weather_str.lower() or "storm" in weather_str.lower()
            
            intel_score = calculate_intelligence_score(
                ev=ev,
                match_count=min(home_match_count, away_match_count),
                overround=vig["overround"],
                risks_found=risks
            )

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
                "intelligence_score": intel_score,
            })

    return value_bets, (model_h, model_d, model_a)



async def detect_value_bets_for_upcoming():
    """
    Background task: scan all upcoming matches and their latest odds,
    run the model, store any value bets found, and send alerts.
    """
    from backend.models import TeamMatchStats
    from sqlalchemy import func
    
    logger.info("Starting value bet scan…")
    detected_count = 0

    async with AsyncSessionLocal() as db:
        # Get current bankroll
        br_result = await db.execute(
            select(Bankroll).order_by(Bankroll.snapshot_at.desc()).limit(1)
        )
        br = br_result.scalar_one_or_none()
        bankroll = br.balance if br else settings.default_bankroll

        # Check Drawdown Protection
        from backend.models import SystemConfig
        cfg_paused = await db.execute(select(SystemConfig).where(SystemConfig.key == "betting_paused"))
        if (paused_obj := cfg_paused.scalar_one_or_none()) and paused_obj.value == "True":
            logger.warning("[Scanner] Betting is PAUSED due to drawdown protection.")
            return 0
            
        cfg_kelly = await db.execute(select(SystemConfig).where(SystemConfig.key == "kelly_fraction_multiplier"))
        kelly_mult = float(cfg_kelly.scalar_one_or_none().value) if cfg_kelly.scalar_one_or_none() else 1.0
        
        effective_kelly = settings.kelly_fraction * kelly_mult
        if kelly_mult < 1.0:
            logger.info(f"[Scanner] Reduced Kelly Fraction in effect: {effective_kelly:.3f}")


        # Get upcoming matches
        matches_result = await db.execute(
            select(Match)
            .options(joinedload(Match.home_team), joinedload(Match.away_team))
            .where(Match.status == "scheduled")
        )
        matches = matches_result.scalars().all()

        for match in matches:
            # Get latest odds per bookmaker
            odds_result = await db.execute(
                select(OddsHistory)
                .where(OddsHistory.match_id == match.id)
                .order_by(OddsHistory.fetched_at.desc())
            )
            all_odds = odds_result.scalars().all()
            if not all_odds: continue

            # Group by selection to find "Best Odds"
            best_prices = {"Home": (0.0, ""), "Draw": (0.0, ""), "Away": (0.0, "")}
            seen_bm = set()
            for o in all_odds:
                if o.bookmaker in seen_bm: continue
                seen_bm.add(o.bookmaker)
                if o.home_odds and o.home_odds > best_prices["Home"][0]:
                    best_prices["Home"] = (o.home_odds, o.bookmaker)
                if o.draw_odds and o.draw_odds > best_prices["Draw"][0]:
                    best_prices["Draw"] = (o.draw_odds, o.bookmaker)
                if o.away_odds and o.away_odds > best_prices["Away"][0]:
                    best_prices["Away"] = (o.away_odds, o.bookmaker)

            # Get match counts for both teams
            hc_res = await db.execute(select(func.count(TeamMatchStats.id)).where(TeamMatchStats.team_id == match.home_team_id))
            ac_res = await db.execute(select(func.count(TeamMatchStats.id)).where(TeamMatchStats.team_id == match.away_team_id))
            home_count = hc_res.scalar() or 0
            away_count = ac_res.scalar() or 0

            # Run detection on the best odds for each selection
            for selection, (price, bm) in best_prices.items():
                if price == 0: continue
                
                vbs, (mh, md, ma) = detect_value_from_odds(
                    home_attack=match.home_team.attack_strength if match.home_team else 1.0,
                    home_defence=match.home_team.defence_strength if match.home_team else 1.0,
                    away_attack=match.away_team.attack_strength if match.away_team else 1.0,
                    away_defence=match.away_team.defence_strength if match.away_team else 1.0,
                    home_elo=match.home_team.elo_rating if match.home_team else 1500.0,
                    away_elo=match.away_team.elo_rating if match.away_team else 1500.0,
                    home_match_count=home_count,
                    away_match_count=away_count,
                    weather_str=match.weather or "",
                    home_odds=best_prices["Home"][0],
                    draw_odds=best_prices["Draw"][0],
                    away_odds=best_prices["Away"][0],
                    bookmaker=bm,
                    match_id=match.id,
                    bankroll=bankroll,
                    kelly_fraction=effective_kelly,
                )

                
                # Filter VBs to only include the one where this BM is the best
                for vb in vbs:
                    if vb["selection"] == selection:
                        row = ValueBet(**vb)
                        db.add(row)
                        detected_count += 1
                        logger.info(f"Value found: {selection} @ {price} on {bm} (EV={vb['ev']:.3f})")

                # Cache probabilities (only once per match)
                match.model_home_prob = mh
                match.model_draw_prob = md
                match.model_away_prob = ma



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
