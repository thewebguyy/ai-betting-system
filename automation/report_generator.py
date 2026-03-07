"""
automation/report_generator.py
Generate Markdown and PDF match/performance reports using Jinja2 + WeasyPrint.
"""

import os
from datetime import datetime, date
from pathlib import Path
from typing import Optional

from jinja2 import Environment, FileSystemLoader, select_autoescape
from loguru import logger

from backend.config import get_settings
from backend.database import AsyncSessionLocal
from backend.models import Bet, ValueBet, Match, Report
from backend.analytics import compute_analytics
from sqlalchemy import select, desc

settings = get_settings()

TEMPLATES_DIR = Path(__file__).parent / "templates"
REPORTS_DIR = Path("reports")
REPORTS_DIR.mkdir(parents=True, exist_ok=True)
TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)

# Create a simple Jinja2 environment
jinja_env = Environment(
    loader=FileSystemLoader(str(TEMPLATES_DIR)),
    autoescape=select_autoescape(["html", "xml"]),
)


def _render_template(template_name: str, **context) -> str:
    """Render a Jinja2 template; fall back to inline if template file missing."""
    try:
        tmpl = jinja_env.get_template(template_name)
        return tmpl.render(**context)
    except Exception:
        # Fallback: render inline
        return _inline_render(template_name, **context)


def _inline_render(template_name: str, **ctx) -> str:
    """Minimal inline rendering when template files aren't present."""
    if "daily" in template_name:
        a = ctx.get("analytics", {})
        return f"""<!DOCTYPE html><html><body>
<h1>Daily Report — {ctx.get('report_date', date.today())}</h1>
<p>Total Bets: {a.get('total_bets',0)} | Won: {a.get('won',0)} | Lost: {a.get('lost',0)}</p>
<p>ROI: {a.get('roi',0):.2f}% | Profit: {a.get('total_profit',0):.2f}</p>
<p>Value Bets Found: {ctx.get('value_bets_count', 0)}</p>
</body></html>"""
    return f"<html><body><h1>Report</h1><pre>{ctx}</pre></body></html>"


async def generate_daily_report() -> str:
    """Generate end-of-day performance report. Returns file path."""
    async with AsyncSessionLocal() as db:
        analytics = await compute_analytics(db)

        # Count value bets detected today
        today = datetime.utcnow().date()
        vb_result = await db.execute(
            select(ValueBet).where(ValueBet.detected_at >= datetime.combine(today, datetime.min.time()))
        )
        value_bets = vb_result.scalars().all()

    report_date = today.strftime("%Y-%m-%d")
    filename = f"daily_report_{report_date}.pdf"
    file_path = REPORTS_DIR / filename
    md_path = REPORTS_DIR / f"daily_report_{report_date}.md"

    # Build Markdown
    md_content = f"""# Daily Betting Report — {report_date}

## Performance Summary
| Metric | Value |
|--------|-------|
| Total Bets | {analytics.total_bets} |
| Won | {analytics.won} |
| Lost | {analytics.lost} |
| Void | {analytics.void} |
| Pending | {analytics.pending} |
| Hit Rate | {analytics.hit_rate:.1f}% |
| Total Staked | {analytics.total_staked:.2f} |
| Profit/Loss | {analytics.total_profit:+.2f} |
| ROI | {analytics.roi:+.2f}% |
| Avg Odds | {analytics.avg_odds:.3f} |

## Value Bets Detected Today
Total: **{len(value_bets)}**
{"Min EV: " + f"{min(v.ev for v in value_bets):.3f}" if value_bets else "None detected today."}

---
*Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}*
"""
    md_path.write_text(md_content, encoding="utf-8")

    # Try to generate PDF via WeasyPrint
    html_content = _inline_render(
        "daily_report.html",
        analytics=analytics.__dict__ if hasattr(analytics, '__dict__') else dict(analytics),
        value_bets_count=len(value_bets),
        report_date=report_date,
    )
    try:
        from weasyprint import HTML
        HTML(string=html_content).write_pdf(str(file_path))
        logger.info(f"PDF report saved: {file_path}")
    except Exception as e:
        logger.warning(f"WeasyPrint PDF generation failed (saving HTML instead): {e}")
        file_path = REPORTS_DIR / f"daily_report_{report_date}.html"
        file_path.write_text(html_content, encoding="utf-8")

    # Save report record to DB
    async with AsyncSessionLocal() as db:
        report = Report(
            report_type="daily",
            title=f"Daily Report — {report_date}",
            file_path=str(file_path),
            content_md=md_content,
        )
        db.add(report)
        await db.commit()

    return str(file_path)


async def generate_match_report(match_id: int) -> Optional[str]:
    """Generate a match intelligence report for a specific match."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Match).where(Match.id == match_id))
        match = result.scalar_one_or_none()
        if not match:
            logger.error(f"Match {match_id} not found.")
            return None

        vb_result = await db.execute(
            select(ValueBet).where(ValueBet.match_id == match_id)
        )
        value_bets = vb_result.scalars().all()

    # Use AI layer to generate report
    try:
        from models.ai_layer import generate_match_intelligence_report
        model_probs = {
            "home": match.model_home_prob or 0,
            "draw": match.model_draw_prob or 0,
            "away": match.model_away_prob or 0,
        }
        vb_dicts = [
            {
                "selection": vb.selection,
                "bookmaker": vb.bookmaker,
                "decimal_odds": vb.decimal_odds,
                "edge": vb.edge,
                "ev": vb.ev,
                "model_prob": vb.model_prob,
                "suggested_stake": vb.suggested_stake,
            }
            for vb in value_bets
        ]
        md_content = await generate_match_intelligence_report(
            home_team=f"Team {match.home_team_id}",
            away_team=f"Team {match.away_team_id}",
            match_date=match.match_date.strftime("%Y-%m-%d %H:%M"),
            home_elo=match.model_home_prob or 1500,
            away_elo=match.model_away_prob or 1500,
            home_form=match.home_form or "",
            away_form=match.away_form or "",
            home_injuries=[],
            away_injuries=[],
            model_probs=model_probs,
            value_bets=vb_dicts,
        )
    except Exception as e:
        logger.warning(f"AI layer unavailable; using basic report: {e}")
        md_content = f"# Match Report — Match ID {match_id}\n\n*AI layer unavailable.*"

    filename = f"match_report_{match_id}_{datetime.utcnow().strftime('%Y%m%d')}.md"
    file_path = REPORTS_DIR / filename
    file_path.write_text(md_content, encoding="utf-8")

    async with AsyncSessionLocal() as db:
        report = Report(
            report_type="match",
            title=f"Match Intelligence — Match {match_id}",
            file_path=str(file_path),
            content_md=md_content,
        )
        db.add(report)
        await db.commit()

    return str(file_path)


async def generate_report_task(report_type: str, match_id: Optional[int] = None) -> str:
    """Unified task dispatcher called from API endpoint."""
    if report_type == "daily":
        return await generate_daily_report()
    elif report_type == "match" and match_id:
        return await generate_match_report(match_id) or ""
    elif report_type == "performance":
        return await generate_daily_report()  # reuse daily for now
    else:
        return ""
