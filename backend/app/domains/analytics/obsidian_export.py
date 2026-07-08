"""
TradingBrain
Analytics - Obsidian Export

Turns saved backtest / forward-test run records (from :class:`ResultsStore`)
into Obsidian-ready markdown: a **daily report** and a **monthly rollup**, both
written under ``<OBSIDIAN_TRADES_DIR>/tradingbrain/`` for the vault to ingest.

Every trade carries its **NSE session** (Open / Mid-morning / Afternoon / Power
hour) so the analyser can see which part of the day is best/worst. All P&L is
shown **net of the full Indian options charge stack** (brokerage + STT +
exchange txn + SEBI + stamp + GST); the aggregate cost drag is reported too.

Author: TradingBrain
"""

from __future__ import annotations

import os
import re
from datetime import datetime, time, timedelta, timezone
from typing import Any

from app.core.config import settings

IST = timezone(timedelta(hours=5, minutes=30))
_ALLOWED_APPS = {"tradingbrain", "alphaedge", "intellitrade", "smart-money-trader"}


# ── time / session helpers ────────────────────────────────────────────────────
def _to_ist(value: str | datetime | None) -> datetime | None:
    """Parse an ISO string / datetime into an IST-aware datetime."""
    if value is None:
        return None
    dt = value if isinstance(value, datetime) else _parse_iso(value)
    if dt is None:
        return None
    if dt.tzinfo is None:            # naive → assume already IST wall-clock
        return dt.replace(tzinfo=IST)
    return dt.astimezone(IST)


def _parse_iso(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


def session_label(moment: datetime | None) -> str:
    """NSE intraday sub-session for a trade's entry time (IST)."""
    if moment is None:
        return "Unknown"
    t = moment.timetz() if moment.tzinfo else moment.time()
    tt = time(t.hour, t.minute)
    if tt < time(9, 15):
        return "Pre-open"
    if tt <= time(10, 15):
        return "Open (09:15-10:15)"
    if tt <= time(13, 0):
        return "Mid-morning (10:15-13:00)"
    if tt <= time(14, 30):
        return "Afternoon (13:00-14:30)"
    if tt <= time(15, 30):
        return "Power hour (14:30-15:30)"
    return "After-hours"


def ist_date(record: dict[str, Any]) -> str:
    """The IST calendar date (YYYY-MM-DD) a run belongs to, from created_at."""
    dt = _to_ist(record.get("created_at"))
    return dt.strftime("%Y-%m-%d") if dt else "unknown"


def ist_month(record: dict[str, Any]) -> str:
    dt = _to_ist(record.get("created_at"))
    return dt.strftime("%Y-%m") if dt else "unknown"


# ── aggregation ───────────────────────────────────────────────────────────────
def _cell(v: Any) -> str:
    return str("—" if v is None or v == "" else v).replace("|", "/").replace("\n", " ")


def _rupees(v: float) -> str:
    return f"{'+' if v >= 0 else '-'}₹{abs(v):,.0f}"


def _group(trades: list[dict[str, Any]], key_fn) -> list[dict[str, Any]]:
    groups: dict[str, dict[str, Any]] = {}
    for tr in trades:
        k = key_fn(tr) or "—"
        g = groups.setdefault(k, {"label": k, "total": 0, "wins": 0, "losses": 0, "net": 0.0})
        pnl = float(tr.get("pnl") or 0.0)
        g["total"] += 1
        if pnl > 0:
            g["wins"] += 1
        elif pnl < 0:
            g["losses"] += 1
        g["net"] += pnl
    for g in groups.values():
        decided = g["wins"] + g["losses"]
        g["win_rate"] = (g["wins"] / decided * 100) if decided else None
    return sorted(groups.values(), key=lambda g: g["net"], reverse=True)


def aggregate(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Roll a set of run records into headline totals + grouped breakdowns."""
    runs: list[dict[str, Any]] = []
    trades: list[dict[str, Any]] = []
    net = costs = 0.0
    total = wins = losses = 0

    for r in records:
        s = r.get("summary", {}) or {}
        e = s.get("equity", {}) or {}
        t = s.get("trades", {}) or {}
        net += float(e.get("net_return", 0.0) or 0.0)
        costs += float(t.get("total_costs", 0.0) or 0.0)
        total += int(t.get("total", 0) or 0)
        wins += int(t.get("wins", 0) or 0)
        losses += int(t.get("losses", 0) or 0)
        runs.append({
            "id": r.get("id"),
            "created_at": r.get("created_at"),
            "run_type": r.get("run_type"),
            "symbol": r.get("symbol"),
            "net_return": float(e.get("net_return", 0.0) or 0.0),
            "return_pct": float(e.get("return_pct", 0.0) or 0.0),
            # stored summary win_rate is a fraction (0-1); express as percent to
            # match totals/by_strategy/by_session which are already 0-100.
            "win_rate": float(t.get("win_rate", 0.0) or 0.0) * 100,
            "total_trades": int(t.get("total", 0) or 0),
            "total_costs": float(t.get("total_costs", 0.0) or 0.0),
            "max_drawdown_pct": float(e.get("max_drawdown_pct", 0.0) or 0.0),
        })
        for tr in r.get("trades", []) or []:
            entry_ist = _to_ist(tr.get("entry_time"))
            trades.append({**tr, "_run_type": r.get("run_type"), "_entry_ist": entry_ist,
                           "_session": session_label(entry_ist)})

    decided = wins + losses
    return {
        "runs": runs,
        "trades": trades,
        "totals": {
            "runs": len(runs),
            "forward_tests": sum(1 for r in runs if r["run_type"] == "forward-test"),
            "backtests": sum(1 for r in runs if r["run_type"] != "forward-test"),
            "trades": total, "wins": wins, "losses": losses,
            "win_rate": (wins / decided * 100) if decided else None,
            "net_pnl": net, "total_costs": costs,
        },
        "by_strategy": _group(trades, lambda tr: tr.get("strategy") or tr.get("structure")),
        "by_session": _group(trades, lambda tr: tr.get("_session")),
    }


# ── markdown builders ─────────────────────────────────────────────────────────
_COST_NOTE = ("Net P&L is **after all NSE options charges** — brokerage, STT, "
              "exchange txn, SEBI, stamp duty and 18% GST.")


def _pct(v: float | None) -> str:
    return "—" if v is None else f"{v:.0f}%"


def _headline(agg: dict[str, Any]) -> str:
    t = agg["totals"]
    return (f"**{t['trades']} trades** across {t['runs']} run(s) "
            f"({t['forward_tests']} forward-test, {t['backtests']} backtest) · "
            f"{t['wins']}W / {t['losses']}L · **{_pct(t['win_rate'])} win** · "
            f"net **{_rupees(t['net_pnl'])}** (after {_rupees(t['total_costs']).lstrip('+')} charges)\n")


def _group_table(title: str, rows: list[dict[str, Any]]) -> str:
    head = title[0].upper() + title[1:]
    out = f"\n## By {title}\n\n| {head} | Trades | Win% | Net P&L |\n|---|---|---|---|\n"
    for r in rows:
        out += f"| {_cell(r['label'])} | {r['total']} | {_pct(r.get('win_rate'))} | {_rupees(r['net'])} |\n"
    return out


def _trades_table(trades: list[dict[str, Any]]) -> str:
    out = ("\n## Trades\n\n| Entry (IST) | Session | Type | Strategy | Structure | Lots | "
           "Exit reason | P&L |\n|---|---|---|---|---|---|---|---|\n")
    for tr in sorted(trades, key=lambda x: x.get("_entry_ist") or datetime.min.replace(tzinfo=IST)):
        ent = tr.get("_entry_ist")
        out += (f"| {ent.strftime('%Y-%m-%d %H:%M') if ent else '—'} | {_cell(tr.get('_session'))} | "
                f"{_cell(tr.get('_run_type'))} | {_cell(tr.get('strategy'))} | {_cell(tr.get('structure'))} | "
                f"{_cell(tr.get('lots'))} | {_cell(tr.get('exit_reason'))} | {_rupees(float(tr.get('pnl') or 0.0))} |\n")
    return out


def _runs_table(runs: list[dict[str, Any]]) -> str:
    out = ("\n## Runs\n\n| Time (IST) | Type | Symbol | Trades | Win% | Net | Costs | MaxDD% |\n"
           "|---|---|---|---|---|---|---|---|\n")
    for r in sorted(runs, key=lambda x: x.get("created_at") or ""):
        dt = _to_ist(r.get("created_at"))
        out += (f"| {dt.strftime('%H:%M') if dt else '—'} | {_cell(r['run_type'])} | {_cell(r['symbol'])} | "
                f"{r['total_trades']} | {_pct(r.get('win_rate'))} | {_rupees(r['net_return'])} | "
                f"₹{r['total_costs']:,.0f} | {r['max_drawdown_pct']:.1f}% |\n")
    return out


# Approximate INR→USD rate — for the cross-app vault dashboard's unified
# net_usd column ONLY. TradingBrain's true P&L is in INR (net_pnl / net_inr);
# this conversion is a convenience so all four apps compare on one axis.
INR_PER_USD = 83.0


def _frontmatter(kind: str, key_field: str, key_value: str, agg: dict[str, Any], tags: list[str]) -> str:
    t = agg["totals"]
    fm = [
        "---", f"type: {kind}", f"app: {settings.OBSIDIAN_APP}", f"{key_field}: {key_value}",
        f"generated: {datetime.now(IST).isoformat(timespec='seconds')}",
        f"runs: {t['runs']}", f"forward_tests: {t['forward_tests']}", f"backtests: {t['backtests']}",
        f"trades: {t['trades']}", f"wins: {t['wins']}", f"losses: {t['losses']}",
        f"win_rate: {'' if t['win_rate'] is None else round(t['win_rate'], 1)}",
        f"net_pnl: {t['net_pnl']:.0f}", f"net_inr: {t['net_pnl']:.0f}",
        f"net_usd: {t['net_pnl'] / INR_PER_USD:.2f}",
        f"total_costs: {t['total_costs']:.0f}",
        "tags:",
    ]
    fm += [f"  - {tag}" for tag in tags]
    fm.append("---\n")
    return "\n".join(fm)


def daily_markdown(records: list[dict[str, Any]], date_str: str) -> str:
    agg = aggregate(records)
    md = _frontmatter("daily-trade-report", "date", date_str, agg,
                      [settings.OBSIDIAN_APP, "daily", "report", date_str])
    md += f"\n# TradingBrain — Daily Report {date_str}\n\n"
    md += _headline(agg)
    md += f"\n> {_COST_NOTE}\n"
    md += _runs_table(agg["runs"])
    md += _group_table("strategy", agg["by_strategy"])
    md += _group_table("session", agg["by_session"])
    md += _trades_table(agg["trades"])
    md += "\n_Generated by TradingBrain for Obsidian ingestion._\n"
    return md


def monthly_markdown(records: list[dict[str, Any]], month_str: str) -> str:
    agg = aggregate(records)
    md = _frontmatter("monthly-trade-summary", "month", month_str, agg,
                      [settings.OBSIDIAN_APP, "monthly", "trades", month_str])
    yr, mo = month_str.split("-")
    month_name = datetime(int(yr), int(mo), 1).strftime("%B")
    md += f"\n# TradingBrain — {month_name} {yr} Trade Summary\n\n"
    md += _headline(agg)
    md += f"\n> {_COST_NOTE}\n"
    # per-day rollup
    by_day: dict[str, list[dict[str, Any]]] = {}
    for r in records:
        by_day.setdefault(ist_date(r), []).append(r)
    md += "\n## By day\n\n| Day | Runs | Trades | Win% | Net | Costs |\n|---|---|---|---|---|---|\n"
    for day in sorted(by_day):
        d = aggregate(by_day[day])["totals"]
        md += (f"| {day} | {d['runs']} | {d['trades']} | {_pct(d['win_rate'])} | "
               f"{_rupees(d['net_pnl'])} | ₹{d['total_costs']:,.0f} |\n")
    md += _group_table("strategy", agg["by_strategy"])
    md += _group_table("session", agg["by_session"])
    md += _trades_table(agg["trades"])
    md += "\n_Generated by TradingBrain for Obsidian ingestion._\n"
    return md


# ── writer ────────────────────────────────────────────────────────────────────
def write_export(rel_name: str, markdown: str, *, subdir: str = "") -> str:
    """Write ``markdown`` to <OBSIDIAN_TRADES_DIR>/<app>/[subdir/]<rel_name>.md.

    ``rel_name`` is validated (YYYY-MM-DD or YYYY-MM) so the path can't escape
    the app folder. Returns the absolute path written.
    """
    app = settings.OBSIDIAN_APP.strip().lower()
    if app not in _ALLOWED_APPS:
        raise ValueError(f"OBSIDIAN_APP '{app}' not in allowed set")
    if not re.fullmatch(r"\d{4}-\d{2}(-\d{2})?", rel_name):
        raise ValueError("rel_name must be YYYY-MM or YYYY-MM-DD")
    if subdir and not re.fullmatch(r"[a-z0-9_-]+", subdir):
        raise ValueError("invalid subdir")

    folder = os.path.join(settings.OBSIDIAN_TRADES_DIR, app, subdir) if subdir \
        else os.path.join(settings.OBSIDIAN_TRADES_DIR, app)
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, f"{rel_name}.md")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(markdown)
    return path
