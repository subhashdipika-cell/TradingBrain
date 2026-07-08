"""
TradingBrain
API - Reports

Daily performance report (aggregated across the day's backtest + forward-test
runs) for the dashboard's Reports tab, plus one-click export of the daily report
and monthly rollup to the Obsidian vault. All figures are net of the full Indian
options charge stack; the aggregate cost drag is reported alongside.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.application.results_store import ResultsStore
from app.core.config import settings
from app.domains.analytics import obsidian_export as ox

router = APIRouter(tags=["Reports"])
_store = ResultsStore(settings.RESULTS_DIR)

IST = timezone(timedelta(hours=5, minutes=30))
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_MONTH_RE = re.compile(r"^\d{4}-\d{2}$")


def _today() -> str:
    return datetime.now(IST).strftime("%Y-%m-%d")


def _this_month() -> str:
    return datetime.now(IST).strftime("%Y-%m")


def _records(*, date: str | None = None, month: str | None = None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for summary in _store.list():
        rec = _store.get(summary.id)
        if rec is None:
            continue
        if date and ox.ist_date(rec) == date:
            out.append(rec)
        elif month and ox.ist_month(rec) == month:
            out.append(rec)
    return out


def _serialisable_trades(agg: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for t in agg["trades"]:
        ent = t.get("_entry_ist")
        rows.append({
            "entry_time": ent.isoformat() if ent else None,
            "session": t.get("_session"),
            "run_type": t.get("_run_type"),
            "strategy": t.get("strategy"),
            "structure": t.get("structure"),
            "lots": t.get("lots"),
            "exit_reason": t.get("exit_reason"),
            "pnl": t.get("pnl"),
        })
    return rows


@router.get("/reports/daily")
async def daily_report(date: str | None = Query(default=None)) -> dict[str, Any]:
    """Aggregated report for one IST trading day (defaults to today)."""
    day = date or _today()
    if not _DATE_RE.match(day):
        raise HTTPException(status_code=400, detail="date must be YYYY-MM-DD")
    agg = ox.aggregate(_records(date=day))
    return {
        "date": day,
        "totals": agg["totals"],
        "runs": agg["runs"],
        "by_strategy": agg["by_strategy"],
        "by_session": agg["by_session"],
        "trades": _serialisable_trades(agg),
    }


@router.post("/reports/daily/export")
async def export_daily(date: str | None = Query(default=None)) -> dict[str, Any]:
    """Write the daily report markdown to the Obsidian vault."""
    day = date or _today()
    if not _DATE_RE.match(day):
        raise HTTPException(status_code=400, detail="date must be YYYY-MM-DD")
    recs = _records(date=day)
    if not recs:
        raise HTTPException(status_code=404, detail=f"No runs found for {day}.")
    path = ox.write_export(day, ox.daily_markdown(recs, day), subdir="daily")
    return {"ok": True, "path": path, "date": day, "runs": len(recs)}


@router.post("/reports/monthly/export")
async def export_monthly(month: str | None = Query(default=None)) -> dict[str, Any]:
    """Write the monthly rollup markdown to the Obsidian vault."""
    m = month or _this_month()
    if not _MONTH_RE.match(m):
        raise HTTPException(status_code=400, detail="month must be YYYY-MM")
    # Monthly rollup = FORWARD TESTS WITH ACTUAL TRADES (the honest live-
    # equivalent). Backtests are synthetic research; zero-trade runs (STAND_ASIDE
    # days, or junk after-hours runs against a closed chain) carry a phantom
    # equity swing with no real trade behind it and would skew the month's net.
    recs = [r for r in _records(month=m)
            if r.get("run_type") == "forward-test" and r.get("trades")]
    if not recs:
        raise HTTPException(status_code=404, detail=f"No forward-test trades found for {m}.")
    path = ox.write_export(m, ox.monthly_markdown(recs, m))
    return {"ok": True, "path": path, "month": m, "runs": len(recs)}
