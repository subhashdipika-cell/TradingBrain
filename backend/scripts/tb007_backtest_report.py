"""
TradingBrain - TB007 weekly backtest reporter (autonomous)

Reruns the Convexity Buy (TB007) strategy across ALL accumulated Dhan
option-chain snapshots and appends a dated read to the Trading_Mind wiki, so
the sample grows week over week and you get a standing answer to "is the edge
real yet?".

Runs three configurations per symbol (net of all NSE charges):
  - directional  (long call/put on the squeeze-break, 2% risk)
  - straddle     (delta-neutral ATM straddle, intraday, 3% risk)
  - straddle-hold (same, held up to 2 sessions overnight, 3% risk)

Writes:
  - <wiki>/strategies/tb007-backtest-tracker.md   (human-readable, newest first)
  - <wiki>/../data/tb007_backtest_history.csv       (machine-readable trend log)

Designed to be run headless by Windows Task Scheduler. It never raises on a
per-symbol failure - it records the error and moves on.

Usage:
    python -m scripts.tb007_backtest_report
    python -m scripts.tb007_backtest_report --data <dir> --wiki <dir> --capital 1000000
"""

from __future__ import annotations

import argparse
import csv
import glob
import os
import re
import sys
import warnings
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime

from app.application.engine import EngineConfig, TradingEngine
from app.domains.execution.costs import IndianOptionsCostModel
from app.domains.execution.historical_feed import OptionChainHistoricalFeed
from app.domains.execution.paper_broker import PaperBroker
from app.domains.market.symbol import get_instrument
from app.domains.portfolio.portfolio import Portfolio
from app.domains.risk.limits import RiskLimits
from app.domains.risk.position_sizing import PositionSizer
from app.domains.risk.risk_engine import RiskEngine
from app.domains.strategy.tb007 import TB007Strategy

warnings.filterwarnings("ignore")

# Task Scheduler / Windows consoles default to cp1252 stdout, which can't encode
# the freshness emoji — force UTF-8 so prints (and the log redirect) never crash.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

DEFAULT_DATA = r"D:/alphaedge/strategy-lab/data/options"
DEFAULT_WIKI = r"E:/Obsidian/Trading_Mind/wiki"
SYMBOLS = ("NIFTY50", "BANKNIFTY", "SENSEX")

TREND_MARKER = "<!-- TREND-ROWS (newest first) -->"
DETAIL_MARKER = "<!-- RUN-DETAILS (newest first) -->"
STATUS_START = "<!-- STATUS-START -->"
STATUS_END = "<!-- STATUS-END -->"

# Data-freshness thresholds (in *trading* days, weekends excluded).
STALE_TRADING_DAYS = 4  # newest session older than this => collector likely down
WATCH_TRADING_DAYS = 2  # a holiday or one-off miss; worth a soft flag

# Hypothesis re-tests that come due when the NIFTY50 sample grows past a
# threshold. The status banner announces them so a filed hypothesis cannot be
# silently forgotten. (threshold_sessions, note)
PENDING_RETESTS = [
    (
        40,
        "**TB005-at-open A/B is due** — hypothesis filed 2026-07-11 at 14 "
        "sessions (open entries flipped TB005 to PF 1.39 while every other "
        "strategy confirmed the 10:15 gate). Re-run: "
        "`python -m scripts.open_gate_ab`. If it still holds, implement a "
        "per-strategy `open_entry_allowed` override — do NOT lift the "
        "platform gate.",
    ),
]


@dataclass
class Result:
    symbol: str
    config: str
    trades: int = 0
    wins: int = 0
    net: float = 0.0
    gross_profit: float = 0.0
    gross_loss: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    max_win: float = 0.0
    max_loss: float = 0.0
    rolls: int = 0
    exits: dict | None = None
    error: str = ""

    @property
    def win_pct(self) -> float:
        return 100.0 * self.wins / self.trades if self.trades else 0.0

    @property
    def payoff(self) -> float:
        return self.avg_win / self.avg_loss if self.avg_loss else 0.0

    @property
    def pf(self) -> float:
        return self.gross_profit / self.gross_loss if self.gross_loss else 0.0

    @property
    def expectancy(self) -> float:
        return self.net / self.trades if self.trades else 0.0


CONFIGS = {
    # label: (neutral_straddle, requested_risk, hold_overnight, max_hold_sessions)
    "directional": (False, 0.02, False, 0),
    "straddle": (True, 0.03, False, 0),
    "straddle-hold2": (True, 0.03, True, 2),
}


def run_one(symbol: str, label: str, params, data_dir: str, capital: float) -> Result:
    neutral, risk, hold, max_sess = params
    res = Result(symbol=symbol, config=label)
    try:
        spec = get_instrument(symbol)
        feed = OptionChainHistoricalFeed.from_dhan_dir(
            data_dir, spec=spec, prefix=symbol
        )
        strat = TB007Strategy()
        strat.configuration.neutral_straddle = neutral
        strat.configuration.requested_risk = risk
        strat.configuration.hold_overnight = hold
        strat.configuration.max_hold_sessions = max_sess
        engine = TradingEngine(
            strategy=strat,
            feed=feed,
            broker=PaperBroker(
                slippage_pct=0.0,
                cost_model=IndianOptionsCostModel(),
                tick_size=spec.tick_size,
            ),
            portfolio=Portfolio(starting_capital=capital),
            risk_engine=RiskEngine(RiskLimits(max_daily_loss=0.04, max_drawdown=0.10)),
            sizer=PositionSizer(),
            config=EngineConfig(bar_minutes=1, capital_allocation=0.25),
        )
        journal = engine.run()
        trades = list(journal.trades)
        res.rolls = sum(1 for _, m in journal.events if m.startswith("HOLD"))
        res.trades = len(trades)
        wins = [t for t in trades if t.pnl > 0]
        losses = [t for t in trades if t.pnl <= 0]
        res.wins = len(wins)
        res.gross_profit = sum(t.pnl for t in wins)
        res.gross_loss = -sum(t.pnl for t in losses)
        res.net = sum(t.pnl for t in trades)
        res.avg_win = res.gross_profit / len(wins) if wins else 0.0
        res.avg_loss = res.gross_loss / len(losses) if losses else 0.0
        res.max_win = max((t.pnl for t in trades), default=0.0)
        res.max_loss = min((t.pnl for t in trades), default=0.0)
        res.exits = dict(Counter(t.exit_reason for t in trades))
    except Exception as exc:  # never crash the weekly job on one symbol
        res.error = f"{type(exc).__name__}: {exc}"
    return res


def aggregate(results: list[Result], label: str) -> Result:
    agg = Result(symbol="ALL", config=label)
    subset = [r for r in results if r.config == label and not r.error]
    agg.trades = sum(r.trades for r in subset)
    agg.wins = sum(r.wins for r in subset)
    agg.net = sum(r.net for r in subset)
    agg.gross_profit = sum(r.gross_profit for r in subset)
    agg.gross_loss = sum(r.gross_loss for r in subset)
    agg.rolls = sum(r.rolls for r in subset)
    agg.avg_win = agg.gross_profit / agg.wins if agg.wins else 0.0
    losers = agg.trades - agg.wins
    agg.avg_loss = agg.gross_loss / losers if losers else 0.0
    agg.max_win = max((r.max_win for r in subset), default=0.0)
    agg.max_loss = min((r.max_loss for r in subset), default=0.0)
    return agg


def data_coverage(data_dir: str) -> tuple[dict, list[str]]:
    cov = {}
    all_dates: set[str] = set()
    for sym in SYMBOLS:
        files = sorted(glob.glob(os.path.join(data_dir, f"{sym}_OPT_*.csv")))
        dates = [
            re.search(r"_OPT_(\d{4}-\d{2}-\d{2})", os.path.basename(f)).group(1)
            for f in files
        ]
        all_dates.update(dates)
        cov[sym] = {"sessions": len(dates), "range": (dates[0], dates[-1]) if dates else ("-", "-")}
    return cov, sorted(all_dates)


# ── Data-freshness guard ──────────────────────────────────────────────────────
@dataclass
class Freshness:
    """A read on whether the upstream Dhan collector is still adding sessions."""

    status: str  # FRESH | WATCH | STALE
    emoji: str
    newest: str
    trading_days_old: int
    distinct: int
    sessions_added: int  # distinct sessions gained since the previous run
    message: str


def _trading_days_between(newest: str, run_date: str) -> int:
    """Weekdays strictly after ``newest`` up to and including ``run_date``."""
    d0 = date.fromisoformat(newest)
    d1 = date.fromisoformat(run_date)
    gap, cur = 0, d0
    while cur < d1:
        cur = date.fromordinal(cur.toordinal() + 1)
        if cur.weekday() < 5:
            gap += 1
    return gap


def read_prev_state(csv_path: str, run_date: str) -> tuple[int | None, str | None]:
    """Return (distinct_sessions, latest_session) from the most recent *earlier*
    run recorded in the history CSV, or (None, None) if unavailable."""
    if not os.path.exists(csv_path):
        return None, None
    with open(csv_path, newline="", encoding="utf-8") as f:
        rows = list(csv.reader(f))
    if len(rows) < 2:
        return None, None
    header = rows[0]
    try:
        di = header.index("distinct_sessions")
        li = header.index("latest_session")
        ri = header.index("run_date")
    except ValueError:
        return None, None  # pre-freshness schema
    cands = [r for r in rows[1:] if len(r) > max(di, li, ri) and r[ri] != run_date]
    if not cands:
        return None, None
    prev = max(cands, key=lambda r: r[ri])  # ISO dates sort lexically
    try:
        return int(prev[di]), prev[li]
    except (ValueError, IndexError):
        return None, None


def assess_freshness(
    all_dates: list[str], run_date: str, prev_distinct: int | None
) -> Freshness:
    distinct = len(all_dates)
    newest = all_dates[-1]
    gap = _trading_days_between(newest, run_date)
    added = distinct - prev_distinct if prev_distinct is not None else distinct
    grew = prev_distinct is None or distinct > prev_distinct

    if gap >= STALE_TRADING_DAYS:
        status, emoji = "STALE", "🛑"
    elif gap >= WATCH_TRADING_DAYS:
        status, emoji = "WATCH", "⚠️"
    else:
        status, emoji = "FRESH", "✅"
    # Week-over-week: if a prior run exists and NOTHING new arrived, that's the
    # collector-stopped signal — but only when at least one TRADING day has
    # passed since the newest session. Two runs across a weekend/holiday (e.g.
    # Sat test run, Sun scheduled run) legitimately see zero growth; the
    # 2026-07-12 Sunday run false-alarmed STALE on data that was current as of
    # Friday's close.
    if prev_distinct is not None and not grew and gap >= 1:
        status, emoji = "STALE", "🛑"

    if status == "FRESH":
        msg = (
            f"data fresh — newest session **{newest}**, "
            f"+{added} session(s) since last run · {distinct} sessions total."
        )
    elif status == "WATCH":
        msg = (
            f"data lagging — newest session **{newest}** is {gap} trading days "
            f"old (holiday?), +{added} since last run · {distinct} total."
        )
    elif prev_distinct is not None and not grew and gap >= 1:
        msg = (
            f"**DATA STALE** — no new sessions since last run (still {distinct}); "
            f"newest **{newest}**. The AlphaEdge Dhan options collector may be "
            "down — check it before trusting these numbers."
        )
    else:
        msg = (
            f"**DATA STALE** — newest session **{newest}** is {gap} trading days "
            f"old. The AlphaEdge Dhan options collector may be down — check it "
            "before trusting these numbers."
        )
    return Freshness(status, emoji, newest, gap, distinct, added, msg)


def status_banner(run_date: str, fresh: Freshness) -> str:
    return f"> {fresh.emoji} **Data status ({run_date}):** {fresh.message}"


def set_status(text: str, banner_md: str) -> str:
    block = f"{STATUS_START}\n{banner_md}\n{STATUS_END}"
    if STATUS_START in text and STATUS_END in text:
        pre = text[: text.index(STATUS_START)]
        post = text[text.index(STATUS_END) + len(STATUS_END):]
        return pre + block + post
    anchor = "## Trend (aggregate, newest first)"
    if anchor in text:
        return text.replace(anchor, block + "\n\n" + anchor, 1)
    return block + "\n\n" + text


def _row(r: Result) -> str:
    if r.error:
        return f"| {r.symbol} · {r.config} | — | — | — | — | — | _{r.error}_ |"
    return (
        f"| {r.symbol} · {r.config} | {r.trades} | {r.win_pct:.0f}% | "
        f"{r.net:,.0f} | {r.payoff:.2f} | {r.pf:.2f} | {r.expectancy:,.0f} |"
    )


def build_detail(
    run_date: str, cov: dict, results: list[Result], aggs: dict, cap: float,
    fresh: Freshness,
) -> str:
    total_sessions = sum(c["sessions"] for c in cov.values())
    cov_str = " / ".join(f"{c['sessions']} {s}" for s, c in cov.items())
    lines = [
        f"## [{run_date}] TB007 backtest — {cov_str} sessions",
        "",
        f"**Data:** {total_sessions} option-chain files "
        f"(NIFTY50 {cov['NIFTY50']['range'][0]}→{cov['NIFTY50']['range'][1]}). "
        f"Capital ₹{cap/1e5:.0f}L · net of all NSE charges.",
        f"**Freshness:** {fresh.emoji} {fresh.message}",
        "",
        "| Symbol · Config | Trades | Win% | Net ₹ | Payoff | PF | Exp/trade ₹ |",
        "|---|---|---|---|---|---|---|",
    ]
    for label in CONFIGS:
        for r in [x for x in results if x.config == label]:
            lines.append(_row(r))
        lines.append(_row(aggs[label]).replace("| ALL ·", "| **ALL** ·").rstrip("|") + "|")
    lines.append("")
    lines.append(
        "_Auto-generated by `scripts/tb007_backtest_report.py`. "
        "Convex strategies need a large sample — read the trend, not one row._"
    )
    lines.append("")
    return "\n".join(lines)


def build_trend_rows(run_date: str, cov: dict, aggs: dict) -> str:
    total_sessions = sum(c["sessions"] for c in cov.values())
    rows = []
    for label in CONFIGS:
        a = aggs[label]
        rows.append(
            f"| {run_date} | {total_sessions} | {label} | {a.trades} | "
            f"{a.win_pct:.0f}% | {a.net:,.0f} | {a.pf:.2f} | {a.rolls} |"
        )
    return "\n".join(rows)


def ensure_page(path: str) -> None:
    if os.path.exists(path):
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    header = f"""---
tags: [strategy, tracker]
last_updated: {date.today().isoformat()}
---

# TB007 Convexity Buy — Backtest Tracker

Standing, auto-updated read on whether [[convexity-buy-tb007]] has a real edge.
A weekly Windows task reruns TB007 across **all** accumulated Dhan option-chain
data and appends a row here. **Read the trend, not any single week** — convex
strategies (lose small often, win big rarely) need a large sample before the
numbers mean anything ([[fooled-by-randomness]]).

Aggregate = NIFTY50 + BANKNIFTY + SENSEX combined. Net % is on ₹10L capital.

{STATUS_START}
_No run yet._
{STATUS_END}

## Trend (aggregate, newest first)

| Run date | Sessions | Config | Trades | Win% | Net ₹ | PF | Rolls |
|---|---|---|---|---|---|---|---|
{TREND_MARKER}

## Weekly runs (newest first)

{DETAIL_MARKER}
"""
    with open(path, "w", encoding="utf-8") as f:
        f.write(header)


def insert_after(text: str, marker: str, block: str) -> str:
    idx = text.index(marker) + len(marker)
    return text[:idx] + "\n" + block + text[idx:]


def remove_existing_run(text: str, run_date: str) -> str:
    """Make same-day re-runs idempotent: drop any trend rows and the detail
    section already recorded for ``run_date`` before inserting the fresh one."""
    # Trend rows: "| <date> | ..."
    text = re.sub(
        rf"(?m)^\| {re.escape(run_date)} \|.*\n", "", text
    )
    # Detail section: "## [<date>] ..." up to the next "## [" (or the trailing
    # end of file), leaving other runs intact.
    text = re.sub(
        rf"(?ms)^## \[{re.escape(run_date)}\].*?(?=^## \[|\Z)", "", text
    )
    return text


def append_history_csv(
    path: str, run_date: str, cov: dict, aggs: dict, fresh: Freshness
) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    header = ["run_date", "latest_session", "distinct_sessions", "sessions",
              "config", "trades", "win_pct", "net", "payoff", "pf",
              "expectancy", "rolls", "freshness"]
    # Idempotent: keep prior rows for OTHER dates (only if they match the
    # current schema — pre-freshness rows are dropped at this one migration).
    prior = []
    if os.path.exists(path):
        with open(path, newline="", encoding="utf-8") as f:
            rows = list(csv.reader(f))
        prior = [
            r for r in rows[1:]
            if r and r[0] != run_date and len(r) == len(header)
        ]
    total_sessions = sum(c["sessions"] for c in cov.values())
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(prior)
        for label in CONFIGS:
            a = aggs[label]
            w.writerow([
                run_date, fresh.newest, fresh.distinct, total_sessions,
                label, a.trades, round(a.win_pct, 1), round(a.net, 0),
                round(a.payoff, 2), round(a.pf, 2), round(a.expectancy, 0),
                a.rolls, fresh.status,
            ])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=DEFAULT_DATA)
    ap.add_argument("--wiki", default=DEFAULT_WIKI)
    ap.add_argument("--capital", type=float, default=1_000_000.0)
    args = ap.parse_args()

    run_date = date.today().isoformat()
    cov, all_dates = data_coverage(args.data)
    if not all_dates:
        print(f"[tb007-report] No option-chain data in {args.data}; nothing to do.")
        return

    hist = os.path.join(os.path.dirname(args.wiki), "data", "tb007_backtest_history.csv")
    prev_distinct, _prev_newest = read_prev_state(hist, run_date)
    fresh = assess_freshness(all_dates, run_date, prev_distinct)

    results: list[Result] = []
    for sym in SYMBOLS:
        for label, params in CONFIGS.items():
            results.append(run_one(sym, label, params, args.data, args.capital))
    aggs = {label: aggregate(results, label) for label in CONFIGS}

    tracker = os.path.join(args.wiki, "strategies", "tb007-backtest-tracker.md")
    ensure_page(tracker)
    with open(tracker, encoding="utf-8") as f:
        text = f.read()
    text = remove_existing_run(text, run_date)  # idempotent same-day re-runs
    banner = status_banner(run_date, fresh)
    nifty_sessions = cov.get("NIFTY50", {}).get("sessions", 0)
    for threshold, note in PENDING_RETESTS:
        if nifty_sessions >= threshold:
            banner += f"\n> 📌 {note}"
    text = set_status(text, banner)
    text = insert_after(text, TREND_MARKER, build_trend_rows(run_date, cov, aggs))
    text = insert_after(
        text, DETAIL_MARKER,
        build_detail(run_date, cov, results, aggs, args.capital, fresh),
    )
    text = re.sub(r"last_updated: .*", f"last_updated: {run_date}", text, count=1)
    with open(tracker, "w", encoding="utf-8") as f:
        f.write(text)

    append_history_csv(hist, run_date, cov, aggs, fresh)

    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[tb007-report] {ts} appended run for {run_date} "
          f"({fresh.distinct} sessions, newest {fresh.newest}) -> {tracker}")
    if fresh.status == "STALE":
        print(f"[tb007-report] *** WARNING: {fresh.status} *** {fresh.message}")
    else:
        print(f"[tb007-report] data {fresh.status} ({fresh.emoji}) "
              f"+{fresh.sessions_added} session(s) since last run")
    for threshold, note in PENDING_RETESTS:
        if nifty_sessions >= threshold:
            print(f"[tb007-report] *** RE-TEST DUE ({threshold}+ sessions) *** "
                  f"{re.sub(r'[*`]', '', note)}")
    for label in CONFIGS:
        a = aggs[label]
        print(f"   {label:16} {a.trades:3} trades  win {a.win_pct:4.0f}%  "
              f"net Rs {a.net:>10,.0f}  PF {a.pf:.2f}  rolls {a.rolls}")


if __name__ == "__main__":
    main()
