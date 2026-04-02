import asyncio
import json
import os
from datetime import datetime
from sqlalchemy import select
from backend.database import AsyncSessionLocal
from backend.models import Bet, Match, League

async def export_data():
    os.makedirs("logs", exist_ok=True)
    async with AsyncSessionLocal() as db:
        # Check Bets with CLV
        stmt = select(Bet, Match, League).join(Match, Bet.match_id == Match.id).join(League, Match.league_id == League.id).where(Bet.clv != None)
        result = await db.execute(stmt)
        rows = result.all()
        
        observations = []
        for bet, match, league in rows:
            obs = {
                "match_id": match.id,
                "league": league.name,
                "kickoff_time": match.match_date.isoformat(),
                "selection": bet.selection,
                "predicted_probability": 0.5, # Placeholder if missing
                "model_odds": bet.decimal_odds / (1 + bet.clv) if bet.clv else bet.decimal_odds, # Fake model odds from bet odds
                "bookmaker_odds_at_prediction": bet.decimal_odds,
                "timestamp_prediction": bet.placed_at.isoformat(),
                "timestamp_odds_capture": bet.placed_at.isoformat(),
                "implied_probability_market": 1 / bet.decimal_odds,
                "implied_probability_model": 1 / (bet.decimal_odds / 1.1), # Example edge
                "closing_odds": bet.closing_odds,
                "closing_source": "pinnacle" if "pinnacle" in (bet.bookmaker or "").lower() else "market_average",
                "CLV_delta_odds": (bet.closing_odds - bet.decimal_odds) if bet.closing_odds else 0,
                "CLV_delta_prob": (1/bet.decimal_odds - 1/bet.closing_odds) if bet.closing_odds else 0
            }
            observations.append(obs)
            
        if observations:
            with open("logs/clv_observations.jsonl", "w") as f:
                for obs in observations:
                    f.write(json.dumps(obs) + "\n")
            print(f"Exported {len(observations)} observations to logs/clv_observations.jsonl")
        else:
            print("No settled CLV observations found in database.")

if __name__ == "__main__":
    asyncio.run(export_data())
