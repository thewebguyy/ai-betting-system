"""
scripts/fixture_selection.py
Fetches today's fixtures and selects optimal betting markets.
"""

import asyncio
import json
from datetime import datetime, timedelta
from loguru import logger
import pandas as pd

# Core Project Imports
from scrapers.data_fetch import fetch_fixtures, fetch_odds_api, normalise_fixture
from backend.config import get_settings

settings = get_settings()

# Top European Leagues (High Liquidity)
LIQUID_LEAGUES = {
    39: "English Premier League",
    140: "La Liga",
    135: "Serie A",
    78: "Bundesliga",
    61: "Ligue 1"
}

class SelectionEngine:
    def __init__(self, fixtures_with_odds):
        self.data = fixtures_with_odds

    def calculate_margin(self, odds):
        if not odds or any(o <= 0 for o in odds): return 1.0
        return sum(1/o for o in odds) - 1.0

    def select_markets(self):
        final_picks = []
        
        for item in self.data:
            match = item['fixture']
            odds_list = item.get('odds', [])
            if not odds_list: continue

            match_safeties = []
            match_goals = []

            for bm in odds_list:
                h, d, a = bm.get('home_odds'), bm.get('draw_odds'), bm.get('away_odds')
                margin = self.calculate_margin([h, d, a] if h and d and a else [])
                stability = 1 - margin

                # --- 1. SAFETIES (1X or DNB) ---
                if h and d:
                    prob_1x = (1/h) + (1/d)
                    if prob_1x >= 0.60:
                        match_safeties.append({
                            "match": f"{match['home_team']} vs {match['away_team']}",
                            "market": "Double Chance (1X)",
                            "odds": round(1/prob_1x, 2),
                            "probability": prob_1x,
                            "stability_score": stability
                        })
                    
                    dnb1_odds = h * (1 - 1/d)
                    if dnb1_odds > 1.0 and (1/dnb1_odds) >= 0.60:
                        match_safeties.append({
                            "match": f"{match['home_team']} vs {match['away_team']}",
                            "market": "Draw No Bet (1)",
                            "odds": round(dnb1_odds, 2),
                            "probability": 1/dnb1_odds,
                            "stability_score": stability
                        })

                # --- 2. GOALS MARKETS (O1.5, U3.5) ---
                totals = bm.get('totals')
                if totals:
                    # Outcomes for 1.5 and 3.5 lines
                    outcomes = {o['name']: o['price'] for o in totals.get('outcomes', [])}
                    
                    # Over 1.5 (Proxy from 2.5 if 1.5 line is missing)
                    o15 = None
                    o_items = [o for o in totals.get('outcomes', []) if o.get('point') == 1.5 and o.get('name') == 'Over']
                    if o_items: o15 = o_items[0]['price']
                    
                    if not o15: # Proxy logic for O1.5
                        o25_items = [o for o in totals.get('outcomes', []) if o.get('point') == 2.5 and o.get('name') == 'Over']
                        if o25_items: o15 = o25_items[0]['price'] * 0.75 # Theoretical adjustment
                    
                    if o15 and (1/o15) >= 0.60:
                        match_goals.append({
                            "match": f"{match['home_team']} vs {match['away_team']}",
                            "market": "Over 1.5 Goals",
                            "odds": round(o15, 2),
                            "probability": 1/o15,
                            "stability_score": stability
                        })

                    # Under 3.5
                    u35 = None
                    u_items = [o for o in totals.get('outcomes', []) if o.get('point') == 3.5 and o.get('name') == 'Under']
                    if u_items: u35 = u_items[0]['price']
                    
                    if not u35: # Proxy logic for U3.5
                        u25_items = [o for o in totals.get('outcomes', []) if o.get('point') == 2.5 and o.get('name') == 'Under']
                        if u25_items: u35 = u25_items[0]['price'] * 1.35 # Theoretical adjustment
                        
                    if u35 and (1/u35) >= 0.60:
                        match_goals.append({
                            "match": f"{match['home_team']} vs {match['away_team']}",
                            "market": "Under 3.5 Goals",
                            "odds": round(u35, 2),
                            "probability": 1/u35,
                            "stability_score": stability
                        })

            # Select Top 1 from each category per match
            if match_safeties:
                match_safeties.sort(key=lambda x: (x['stability_score'], x['probability']), reverse=True)
                final_picks.append(match_safeties[0])
            if match_goals:
                match_goals.sort(key=lambda x: (x['stability_score'], x['probability']), reverse=True)
                final_picks.append(match_goals[0])

        df = pd.DataFrame(final_picks)
        if df.empty: return df
        return df.sort_values(by=["stability_score", "probability"], ascending=False)

async def main():
    logger.info("Fetching fixtures and core markets (H2H, Totals)...")
    
    all_results = []
    now = datetime.utcnow()
    limit_24h = now + timedelta(hours=24)

    sport_map = {
        "soccer_epl": "English Premier League",
        "soccer_spain_la_liga": "La Liga",
        "soccer_italy_serie_a": "Serie A",
        "soccer_germany_bundesliga": "Bundesliga",
        "soccer_france_ligue_one": "Ligue 1"
    }

    for sport_key, league_name in sport_map.items():
        try:
            # Fetch H2H and Totals in bulk
            odds_data = await fetch_odds_api(sport=sport_key, markets="h2h,totals")
            
            for o in odds_data:
                kickoff = datetime.fromisoformat(o['commence_time'].replace('Z', '+00:00')).replace(tzinfo=None)
                if now <= kickoff <= limit_24h:
                    match_odds = []
                    for bm in o.get('bookmakers', []):
                        h2h = next((m for m in bm.get('markets', []) if m['key'] == 'h2h'), None)
                        totals = next((m for m in bm.get('markets', []) if m['key'] == 'totals'), None)
                        
                        if h2h:
                            outcomes = {out['name']: out['price'] for out in h2h['outcomes']}
                            match_odds.append({
                                "bookmaker": bm['key'],
                                "home_odds": outcomes.get(o['home_team']),
                                "draw_odds": outcomes.get("Draw"),
                                "away_odds": outcomes.get(o['away_team']),
                                "totals": totals
                            })
                    
                    all_results.append({
                        "fixture": {
                            "home_team": o['home_team'], "away_team": o['away_team'],
                            "match_date": o['commence_time'], "league_id": league_name
                        },
                        "odds": match_odds
                    })
        except Exception as e:
            logger.error(f"Error fetching {sport_key}: {e}")

    engine = SelectionEngine(all_results)
    final_picks = engine.select_markets()

    print("\n" + "="*90)
    print("      DAILY SELECTION ENGINE - DUAL-STRATEGY PICKS (SAFETY + GOALS)")
    print("="*90 + "\n")

    if final_picks.empty:
        print("No picks found meeting the confidence criteria.")
    else:
        # Structured List Output
        output_df = final_picks[['match', 'market', 'odds', 'probability', 'stability_score']]
        # Round probability for display
        output_df['probability'] = output_df['probability'].map(lambda x: f"{x:.1%}")
        print(output_df.head(20).to_string(index=False))

    print("\n" + "="*90)

if __name__ == "__main__":
    asyncio.run(main())
