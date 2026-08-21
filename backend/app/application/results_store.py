"""
TradingBrain
Application - Results Store

Persists backtest and forward-test runs to disk as JSON so they can be listed,
compared and re-opened from the dashboard's analysis page. Intentionally
simple (one file per run); a DB-backed store can implement the same interface
later.

Author: TradingBrain
"""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from app.domains.analytics.journal import TradeJournal
from app.domains.analytics.paper_promotion import PaperPromotionTracker
from app.domains.analytics.reports import build_summary
from app.domains.analytics.time_window import TimeWindowTracker


@dataclass(frozen=True, slots=True)
class ResultSummary:
    id: str
    created_at: str
    run_type: str  # "backtest" | "dhan-backtest" | "forward-test"
    symbol: str
    net_return: float
    return_pct: float
    win_rate: float
    profit_factor: float
    max_drawdown_pct: float
    sharpe: float
    total_trades: int
    total_costs: float


class ResultsStore:
    """JSON-file store of run results."""

    def __init__(self, directory: str) -> None:
        self._dir = directory
        os.makedirs(self._dir, exist_ok=True)
        self.time_window_tracker = TimeWindowTracker(
            os.path.join(self._dir, "time_window_stats.json")
        )
        self.paper_promotion_tracker = PaperPromotionTracker(
            os.path.join(self._dir, "paper_promotion_stats.json")
        )

    # ------------------------------------------------------------------
    def save(
        self,
        *,
        run_type: str,
        symbol: str,
        journal: TradeJournal,
        report: str,
        params: dict[str, Any] | None = None,
    ) -> ResultSummary:
        summary = build_summary(journal)
        run_id = datetime.now().strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6]
        created_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

        record = {
            "id": run_id,
            "created_at": created_at,
            "run_type": run_type,
            "symbol": symbol,
            "params": params or {},
            "summary": summary,
            "report": report,
            "equity_curve": [
                {"timestamp": p.timestamp.isoformat(), "equity": p.equity}
                for p in journal.equity_curve
            ],
            "trades": [
                {
                    "symbol": t.symbol,
                    "structure": t.structure,
                    "strategy": t.strategy,
                    "entry_time": t.entry_time.isoformat(),
                    "exit_time": t.exit_time.isoformat(),
                    "pnl": t.pnl,
                    "commission": t.commission,
                    "exit_reason": t.exit_reason,
                    "lots": t.lots,
                }
                for t in journal.trades
            ],
        }
        with open(self._path(run_id), "w", encoding="utf-8") as fh:
            json.dump(record, fh, indent=2)
        if run_type == "forward-test":
            self.time_window_tracker.ingest_journal(run_id, journal)
            starting_capital = float(
                (params or {}).get("starting_capital")
                or summary["equity"]["starting"]
            )
            self.paper_promotion_tracker.ingest_journal(
                run_id,
                journal,
                starting_capital=starting_capital,
            )
        return self._to_summary(record)

    def list(self) -> list[ResultSummary]:
        records: list[ResultSummary] = []
        for name in os.listdir(self._dir):
            if not name.endswith(".json"):
                continue
            try:
                with open(os.path.join(self._dir, name), encoding="utf-8") as fh:
                    records.append(self._to_summary(json.load(fh)))
            except (json.JSONDecodeError, KeyError, OSError):
                continue
        records.sort(key=lambda r: r.created_at, reverse=True)
        return records

    def get(self, run_id: str) -> dict[str, Any] | None:
        path = self._path(run_id)
        if not os.path.isfile(path):
            return None
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)

    # ------------------------------------------------------------------
    def _path(self, run_id: str) -> str:
        safe = "".join(c for c in run_id if c.isalnum() or c in "-_")
        return os.path.join(self._dir, f"{safe}.json")

    @staticmethod
    def _to_summary(record: dict[str, Any]) -> ResultSummary:
        t = record["summary"]["trades"]
        e = record["summary"]["equity"]
        return ResultSummary(
            id=record["id"],
            created_at=record["created_at"],
            run_type=record["run_type"],
            symbol=record["symbol"],
            net_return=e["net_return"],
            return_pct=e["return_pct"],
            win_rate=t["win_rate"],
            profit_factor=t["profit_factor"],
            max_drawdown_pct=e["max_drawdown_pct"],
            sharpe=e["sharpe"],
            total_trades=t["total"],
            total_costs=t["total_costs"],
        )
