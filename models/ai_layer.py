"""
models/ai_layer.py
AI Reasoning Layer using LangChain to chain multiple LLMs.

Pipeline:
  1. Gemini — Extract and summarise structured stats from raw text
  2. Claude  — Estimate probabilities and suggest betting strategy
  3. Grok    — Sentiment analysis from news/social signals
  4. DeepSeek — Statistical modelling assistance

All results cached in Redis to avoid API overuse.
"""

import hashlib
import json
from typing import Optional
from loguru import logger

from backend.config import get_settings
from backend.cache import cache_get, cache_set

settings = get_settings()

# ─── LLM helpers (graceful no-op if keys not configured) ─────────────────────

async def call_gemini(prompt: str, cache_ttl: int = 3600) -> str:
    """Call Google Gemini (free tier available at aistudio.google.com)."""
    cache_key = f"ai:gemini:{hashlib.md5(prompt.encode()).hexdigest()}"
    cached = await cache_get(cache_key)
    if cached:
        return cached

    if not settings.gemini_api_key:
        return "[Gemini key not configured]"

    try:
        from langchain_google_genai import ChatGoogleGenerativeAI
        from langchain_core.messages import HumanMessage
        import os
        os.environ["GOOGLE_API_KEY"] = settings.gemini_api_key
        llm = ChatGoogleGenerativeAI(model="gemini-1.5-flash", temperature=0.1)
        response = await llm.ainvoke([HumanMessage(content=prompt)])
        result = response.content
        await cache_set(cache_key, result, ttl=cache_ttl)
        return result
    except Exception as e:
        logger.warning(f"Gemini call failed: {e}")
        return f"[Gemini error: {e}]"


async def call_claude(prompt: str, cache_ttl: int = 3600) -> str:
    """Call Anthropic Claude (free plan via API)."""
    cache_key = f"ai:claude:{hashlib.md5(prompt.encode()).hexdigest()}"
    cached = await cache_get(cache_key)
    if cached:
        return cached

    if not settings.anthropic_api_key:
        return "[Claude key not configured]"

    try:
        import anthropic
        client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        message = await client.messages.create(
            model="claude-3-haiku-20240307",  # fastest/cheapest free-tier model
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        result = message.content[0].text
        await cache_set(cache_key, result, ttl=cache_ttl)
        return result
    except Exception as e:
        logger.warning(f"Claude call failed: {e}")
        return f"[Claude error: {e}]"


async def call_deepseek(prompt: str, cache_ttl: int = 3600) -> str:
    """Call DeepSeek via OpenAI-compatible API."""
    cache_key = f"ai:deepseek:{hashlib.md5(prompt.encode()).hexdigest()}"
    cached = await cache_get(cache_key)
    if cached:
        return cached

    if not settings.deepseek_api_key:
        return "[DeepSeek key not configured]"

    try:
        from openai import AsyncOpenAI
        client = AsyncOpenAI(
            api_key=settings.deepseek_api_key,
            base_url=settings.deepseek_base_url,
        )
        response = await client.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1024,
            temperature=0.1,
        )
        result = response.choices[0].message.content
        await cache_set(cache_key, result, ttl=cache_ttl)
        return result
    except Exception as e:
        logger.warning(f"DeepSeek call failed: {e}")
        return f"[DeepSeek error: {e}]"


# ─── High-level chained pipelines ─────────────────────────────────────────────

async def extract_match_stats(raw_text: str) -> dict:
    """
    Step 1: Use Gemini to extract structured stats from unstructured text.
    Returns JSON with key stats.
    """
    prompt = f"""Extract the following structured data from this sports text and return ONLY valid JSON:
{{
  "goals_scored_avg": <float or null>,
  "goals_conceded_avg": <float or null>,
  "possession_avg": <float or null>,
  "form_last5": <string like "W,D,L,W,W" or null>,
  "key_players_out": [<list of strings>],
  "sentiment": <"positive"|"negative"|"neutral">
}}

Text:
{raw_text[:2000]}
"""
    response = await call_gemini(prompt)
    try:
        # Strip markdown code fences if present
        clean = response.strip().strip("```json").strip("```").strip()
        return json.loads(clean)
    except Exception:
        return {"raw": response}


async def analyse_bet_strategy(
    match_summary: str,
    home_prob: float,
    draw_prob: float,
    away_prob: float,
    best_odds: dict,
) -> str:
    """
    Step 2: Use Claude to analyse and recommend a betting strategy.
    """
    prompt = f"""You are a professional sports bettor with expertise in value betting.

Match summary: {match_summary}

Model probabilities:
- Home win: {home_prob:.1%}
- Draw: {draw_prob:.1%}
- Away win: {away_prob:.1%}

Best available odds:
{json.dumps(best_odds, indent=2)}

Analyse the value in each market given these probabilities. Identify:
1. Which selection(s) offer positive expected value
2. Recommended stake sizing approach
3. Key risks to consider
4. Overall confidence level (1-5)

Be concise and data-driven. Format as bullet points.
"""
    return await call_claude(prompt)


async def get_sentiment_analysis(team_name: str, news_text: str) -> dict:
    """
    Step 3: Use DeepSeek (or Gemini fallback) for sentiment/news analysis.
    """
    prompt = f"""Analyse the following news about {team_name} from a sports betting perspective.
Rate the impact on their next match performance on a scale of -5 (very negative) to +5 (very positive).
Return ONLY valid JSON:
{{
  "sentiment_score": <int -5 to 5>,
  "key_factors": [<list of strings>],
  "injury_impact": <"high"|"medium"|"low"|"none">,
  "confidence": <"high"|"medium"|"low">,
  "summary": <one sentence>
}}

News text:
{news_text[:1500]}
"""
    response = await call_deepseek(prompt)
    try:
        clean = response.strip().strip("```json").strip("```").strip()
        return json.loads(clean)
    except Exception:
        # Fallback to Gemini
        response = await call_gemini(prompt)
        try:
            clean = response.strip().strip("```json").strip("```").strip()
            return json.loads(clean)
        except Exception:
            return {"raw": response}


async def generate_match_intelligence_report(
    home_team: str, away_team: str,
    match_date: str,
    home_elo: float, away_elo: float,
    home_form: str, away_form: str,
    home_injuries: list[str], away_injuries: list[str],
    model_probs: dict,
    value_bets: list[dict],
) -> str:
    """
    Full AI pipeline: Generate a complete match intelligence report in Markdown.
    Uses Gemini for structuring, Claude for strategy.
    """
    # Build context string
    context = f"""
Match: {home_team} vs {away_team} on {match_date}
ELO: {home_team}={home_elo:.0f}, {away_team}={away_elo:.0f}
Form (last 5): {home_team}: {home_form} | {away_team}: {away_form}
Injuries: {home_team}: {', '.join(home_injuries) or 'None'} | {away_team}: {', '.join(away_injuries) or 'None'}
Model probabilities: Home={model_probs.get('home', 0):.1%} Draw={model_probs.get('draw', 0):.1%} Away={model_probs.get('away', 0):.1%}
Value bets detected: {len(value_bets)}
"""

    # Get strategy from Claude
    strategy = await call_claude(
        f"Write a concise 3-paragraph betting intelligence report for this match:\n{context}\nBe factual and data-driven."
    )

    # Build markdown
    report_md = f"""# Match Intelligence Report
## {home_team} vs {away_team}
**Date:** {match_date}

---

### Team Ratings
| Metric | {home_team} | {away_team} |
|--------|------------|------------|
| ELO Rating | {home_elo:.0f} | {away_elo:.0f} |
| Recent Form | {home_form} | {away_form} |
| Injuries | {len(home_injuries)} | {len(away_injuries)} |

### Model Probabilities
| Outcome | Probability |
|---------|------------|
| {home_team} Win | {model_probs.get('home', 0):.1%} |
| Draw | {model_probs.get('draw', 0):.1%} |
| {away_team} Win | {model_probs.get('away', 0):.1%} |

### AI Analysis
{strategy}

### Value Bets Detected
"""
    if value_bets:
        report_md += "\n| Selection | Odds | Edge | EV | Kelly Stake |\n|-----------|------|------|----|-------------|\n"
        for vb in value_bets:
            report_md += (
                f"| {vb['selection']} ({vb['bookmaker']}) | "
                f"{vb['decimal_odds']} | {vb['edge']:.2%} | "
                f"{vb['ev']:.3f} | {vb['suggested_stake']:.2f} |\n"
            )
    else:
        report_md += "\n*No value bets detected in this match.*\n"

    report_md += "\n---\n*Generated by AI Betting Intelligence System*"
    return report_md
