"""Persistent entry-time statistics and evidence-based promotion gate."""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from app.domains.analytics.journal import TradeJournal, TradeRecord


@dataclass(frozen=True, slots=True)
class PromotionConfig:
    """Minimum evidence required before a time filter can affect entries."""

    bucket_minutes: int = 30
    min_trades: int = 30
    min_sessions: int = 15
    min_expectancy: float = 0.0
    min_profit_factor: float = 1.10
    min_win_rate: float = 0.40


@dataclass(frozen=True, slots=True)
class PromotionDecision:
    symbol: str
    bucket: str
    approved: bool
    trades: int
    sessions: int
    expectancy: float
    profit_factor: float
    win_rate: float
    reasons: tuple[str, ...]


class TimeWindowTracker:
    """Idempotently aggregates completed forward-test trades by entry window."""

    def __init__(self, path: str, config: PromotionConfig | None = None) -> None:
        self.path = path
        self.config = config or PromotionConfig()
        self._recorded_trade_ids: set[str] = set()
        self._data: dict[str, dict[str, dict[str, Any]]] = {}
        self._load()

    def ingest_journal(self, run_id: str, journal: TradeJournal) -> int:
        added = 0
        for index, trade in enumerate(journal.trades):
            trade_id = f"{run_id}:{index}:{trade.entry_time.isoformat()}"
            if trade_id in self._recorded_trade_ids:
                continue
            self.record_trade(trade, trade_id=trade_id)
            added += 1
        if added:
            self._save()
        return added

    def record_trade(self, trade: TradeRecord, *, trade_id: str) -> None:
        if trade_id in self._recorded_trade_ids:
            return
        symbol = trade.symbol.upper()
        bucket = self.bucket_for(trade.entry_time)
        stats = self._data.setdefault(symbol, {}).setdefault(bucket, self._empty_bucket())
        stats["trades"] += 1
        stats["wins"] += int(trade.pnl > 0)
        stats["net_pnl"] += float(trade.pnl)
        stats["gross_profit"] += max(float(trade.pnl), 0.0)
        stats["gross_loss"] += max(-float(trade.pnl), 0.0)
        stats["sessions"].add(trade.entry_time.date().isoformat())
        stats["last_trade"] = trade.entry_time.isoformat()
        self._recorded_trade_ids.add(trade_id)

    def bucket_for(self, timestamp: datetime) -> str:
        minutes = timestamp.hour * 60 + timestamp.minute
        start = (minutes // self.config.bucket_minutes) * self.config.bucket_minutes
        end = start + self.config.bucket_minutes
        return f"{start // 60:02d}:{start % 60:02d}-{end // 60:02d}:{end % 60:02d}"

    def symbols(self) -> tuple[str, ...]:
        return tuple(sorted(self._data))

    def stats(self, symbol: str, bucket: str) -> dict[str, Any]:
        raw = self._data.get(symbol.upper(), {}).get(bucket)
        if raw is None:
            return self._empty_bucket()
        return self._public_stats(raw)

    def decisions(self, symbol: str) -> tuple[PromotionDecision, ...]:
        return tuple(
            self.evaluate(symbol, bucket)
            for bucket in sorted(self._data.get(symbol.upper(), {}))
        )

    def evaluate(self, symbol: str, bucket: str) -> PromotionDecision:
        stats = self.stats(symbol, bucket)
        trades = int(stats["trades"])
        sessions = int(stats["sessions"])
        net_pnl = float(stats["net_pnl"])
        expectancy = net_pnl / trades if trades else 0.0
        gross_loss = float(stats["gross_loss"])
        gross_profit = float(stats["gross_profit"])
        profit_factor = gross_profit / gross_loss if gross_loss else (float("inf") if gross_profit else 0.0)
        win_rate = int(stats["wins"]) / trades if trades else 0.0
        reasons: list[str] = []
        if trades < self.config.min_trades:
            reasons.append(f"trades {trades} < {self.config.min_trades}")
        if sessions < self.config.min_sessions:
            reasons.append(f"sessions {sessions} < {self.config.min_sessions}")
        if expectancy <= self.config.min_expectancy:
            reasons.append(f"expectancy {expectancy:.2f} <= {self.config.min_expectancy:.2f}")
        if profit_factor < self.config.min_profit_factor:
            reasons.append(f"profit factor {profit_factor:.2f} < {self.config.min_profit_factor:.2f}")
        if win_rate < self.config.min_win_rate:
            reasons.append(f"win rate {win_rate:.1%} < {self.config.min_win_rate:.1%}")
        return PromotionDecision(
            symbol=symbol.upper(), bucket=bucket, approved=not reasons,
            trades=trades, sessions=sessions, expectancy=expectancy,
            profit_factor=profit_factor, win_rate=win_rate,
            reasons=tuple(reasons),
        )

    def allow_entry(self, symbol: str, timestamp: datetime) -> bool:
        """Allow all windows until one or more windows are actually promoted."""
        decisions = self.decisions(symbol)
        promoted = {d.bucket for d in decisions if d.approved}
        if not promoted:
            return True
        return self.bucket_for(timestamp) in promoted

    def promotion_report(self, symbol: str) -> list[dict[str, Any]]:
        return [
            {
                "symbol": decision.symbol,
                "bucket": decision.bucket,
                "approved": decision.approved,
                "trades": decision.trades,
                "sessions": decision.sessions,
                "expectancy": decision.expectancy,
                "profit_factor": decision.profit_factor,
                "win_rate": decision.win_rate,
                "reasons": list(decision.reasons),
            }
            for decision in self.decisions(symbol)
        ]

    def _load(self) -> None:
        try:
            with open(self.path, encoding="utf-8") as fh:
                payload = json.load(fh)
        except (FileNotFoundError, OSError, json.JSONDecodeError):
            return
        self._recorded_trade_ids = set(payload.get("trade_ids", []))
        for symbol, buckets in payload.get("symbols", {}).items():
            self._data[symbol] = {}
            for bucket, raw in buckets.items():
                restored = self._empty_bucket()
                restored.update(raw)
                restored["sessions"] = set(raw.get("sessions", []))
                self._data[symbol][bucket] = restored

    def _save(self) -> None:
        os.makedirs(os.path.dirname(os.path.abspath(self.path)), exist_ok=True)
        payload = {
            "version": 1,
            "updated_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
            "trade_ids": sorted(self._recorded_trade_ids),
            "symbols": {
                symbol: {
                    bucket: {
                        **self._public_stats(stats),
                        "sessions": sorted(stats["sessions"]),
                    }
                    for bucket, stats in buckets.items()
                }
                for symbol, buckets in self._data.items()
            },
        }
        fd, temp_path = tempfile.mkstemp(prefix="time-window-", suffix=".json", dir=os.path.dirname(os.path.abspath(self.path)))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, indent=2)
            os.replace(temp_path, self.path)
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)

    @staticmethod
    def _empty_bucket() -> dict[str, Any]:
        return {
            "trades": 0, "wins": 0, "net_pnl": 0.0,
            "gross_profit": 0.0, "gross_loss": 0.0,
            "sessions": set(), "last_trade": None,
        }

    @staticmethod
    def _public_stats(stats: dict[str, Any]) -> dict[str, Any]:
        return {key: value for key, value in stats.items() if key != "sessions"} | {
            "sessions": len(stats["sessions"]),
        }
