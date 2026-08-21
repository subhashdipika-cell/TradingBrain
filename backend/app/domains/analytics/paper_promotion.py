"""Persistent strategy-level promotion gate for completed PAPER forward trades."""

from __future__ import annotations

import json
import math
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from app.domains.analytics.journal import TradeJournal


@dataclass(frozen=True, slots=True)
class PaperPromotionConfig:
    """Conservative evidence thresholds for controlled PAPER scaling."""

    min_trades: int = 50
    min_sessions: int = 20
    min_profitable_session_rate: float = 0.50
    min_expectancy: float = 0.0
    min_profit_factor: float = 1.20
    max_drawdown_pct: float = 0.05
    max_single_loss_pct: float = 0.01


@dataclass(frozen=True, slots=True)
class PaperPromotionDecision:
    symbol: str
    strategy: str
    status: str
    approved_for_paper_scaling: bool
    live_authorized: bool
    trades: int
    sessions: int
    wins: int
    win_rate: float
    profitable_session_rate: float
    net_pnl: float
    expectancy: float
    profit_factor: float
    max_drawdown: float
    max_drawdown_pct: float
    largest_loss: float
    largest_loss_pct: float
    last_trade: str | None
    reasons: tuple[str, ...]


class PaperPromotionTracker:
    """Idempotently aggregate only PAPER forward-test outcomes by strategy."""

    def __init__(
        self, path: str, config: PaperPromotionConfig | None = None
    ) -> None:
        self.path = path
        self.config = config or PaperPromotionConfig()
        self._recorded_trade_ids: set[str] = set()
        self._data: dict[str, dict[str, dict[str, Any]]] = {}
        self._load()

    def ingest_journal(
        self,
        run_id: str,
        journal: TradeJournal,
        *,
        starting_capital: float,
    ) -> int:
        """Record completed trades from one persisted forward-test run."""
        if starting_capital <= 0:
            raise ValueError("starting_capital must be positive")
        added = 0
        for index, trade in enumerate(journal.trades):
            trade_id = f"{run_id}:{index}:{trade.entry_time.isoformat()}"
            if trade_id in self._recorded_trade_ids:
                continue
            symbol = trade.symbol.upper()
            strategy = trade.strategy.upper()
            stats = self._data.setdefault(symbol, {}).setdefault(
                strategy, self._empty_strategy()
            )
            pnl = float(trade.pnl)
            session = trade.entry_time.date().isoformat()
            stats["trades"] += 1
            stats["wins"] += int(pnl > 0)
            stats["net_pnl"] += pnl
            stats["gross_profit"] += max(pnl, 0.0)
            stats["gross_loss"] += max(-pnl, 0.0)
            stats["session_pnl"][session] = stats["session_pnl"].get(session, 0.0) + pnl
            stats["pnl_path"].append(pnl)
            stats["capital_floor"] = min(
                float(stats["capital_floor"]) if stats["capital_floor"] else starting_capital,
                starting_capital,
            )
            stats["largest_loss"] = min(float(stats["largest_loss"]), pnl)
            stats["last_trade"] = trade.exit_time.isoformat()
            self._recorded_trade_ids.add(trade_id)
            added += 1
        if added:
            self._save()
        return added

    def symbols(self) -> tuple[str, ...]:
        return tuple(sorted(self._data))

    def decisions(self, symbol: str | None = None) -> tuple[PaperPromotionDecision, ...]:
        symbols = [symbol.upper()] if symbol else list(self.symbols())
        return tuple(
            self.evaluate(name, strategy)
            for name in symbols
            for strategy in sorted(self._data.get(name, {}))
        )

    def evaluate(self, symbol: str, strategy: str) -> PaperPromotionDecision:
        raw = self._data.get(symbol.upper(), {}).get(strategy.upper(), self._empty_strategy())
        trades = int(raw["trades"])
        wins = int(raw["wins"])
        sessions = len(raw["session_pnl"])
        profitable_sessions = sum(float(pnl) > 0 for pnl in raw["session_pnl"].values())
        profitable_session_rate = profitable_sessions / sessions if sessions else 0.0
        net_pnl = float(raw["net_pnl"])
        expectancy = net_pnl / trades if trades else 0.0
        gross_profit = float(raw["gross_profit"])
        gross_loss = float(raw["gross_loss"])
        profit_factor = gross_profit / gross_loss if gross_loss else (float("inf") if gross_profit else 0.0)
        win_rate = wins / trades if trades else 0.0
        max_drawdown = self._max_drawdown(raw["pnl_path"])
        capital = float(raw["capital_floor"] or 0.0)
        max_drawdown_pct = max_drawdown / capital if capital else 0.0
        largest_loss = float(raw["largest_loss"])
        largest_loss_pct = abs(min(largest_loss, 0.0)) / capital if capital else 0.0

        reasons: list[str] = []
        cfg = self.config
        if trades < cfg.min_trades:
            reasons.append(f"trades {trades} < {cfg.min_trades}")
        if sessions < cfg.min_sessions:
            reasons.append(f"sessions {sessions} < {cfg.min_sessions}")
        if profitable_session_rate < cfg.min_profitable_session_rate:
            reasons.append(
                f"profitable sessions {profitable_session_rate:.1%} < "
                f"{cfg.min_profitable_session_rate:.1%}"
            )
        if expectancy <= cfg.min_expectancy:
            reasons.append(f"expectancy {expectancy:.2f} <= {cfg.min_expectancy:.2f}")
        if profit_factor < cfg.min_profit_factor:
            reasons.append(
                f"profit factor {profit_factor:.2f} < {cfg.min_profit_factor:.2f}"
            )
        if max_drawdown_pct > cfg.max_drawdown_pct:
            reasons.append(
                f"drawdown {max_drawdown_pct:.1%} > {cfg.max_drawdown_pct:.1%}"
            )
        if largest_loss_pct > cfg.max_single_loss_pct:
            reasons.append(
                f"largest loss {largest_loss_pct:.1%} > {cfg.max_single_loss_pct:.1%}"
            )

        approved = not reasons
        return PaperPromotionDecision(
            symbol=symbol.upper(),
            strategy=strategy.upper(),
            status="PAPER_PROMOTED" if approved else "EVIDENCE_REQUIRED",
            approved_for_paper_scaling=approved,
            live_authorized=False,
            trades=trades,
            sessions=sessions,
            wins=wins,
            win_rate=win_rate,
            profitable_session_rate=profitable_session_rate,
            net_pnl=net_pnl,
            expectancy=expectancy,
            profit_factor=profit_factor,
            max_drawdown=max_drawdown,
            max_drawdown_pct=max_drawdown_pct,
            largest_loss=largest_loss,
            largest_loss_pct=largest_loss_pct,
            last_trade=raw["last_trade"],
            reasons=tuple(reasons),
        )

    def report(self, symbol: str | None = None) -> list[dict[str, Any]]:
        from dataclasses import asdict

        report: list[dict[str, Any]] = []
        for decision in self.decisions(symbol):
            row = asdict(decision)
            if not math.isfinite(float(row["profit_factor"])):
                row["profit_factor"] = None
            report.append(row)
        return report

    def _load(self) -> None:
        try:
            with open(self.path, encoding="utf-8") as fh:
                payload = json.load(fh)
        except (FileNotFoundError, OSError, json.JSONDecodeError):
            return
        self._recorded_trade_ids = set(payload.get("trade_ids", []))
        for symbol, strategies in payload.get("symbols", {}).items():
            self._data[symbol] = {}
            for strategy, raw in strategies.items():
                restored = self._empty_strategy()
                restored.update(raw)
                self._data[symbol][strategy] = restored

    def _save(self) -> None:
        directory = os.path.dirname(os.path.abspath(self.path))
        os.makedirs(directory, exist_ok=True)
        payload = {
            "version": 1,
            "scope": "PAPER_FORWARD_ONLY",
            "live_authorized": False,
            "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "trade_ids": sorted(self._recorded_trade_ids),
            "symbols": self._data,
        }
        fd, temp_path = tempfile.mkstemp(
            prefix="paper-promotion-", suffix=".json", dir=directory
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, indent=2)
            os.replace(temp_path, self.path)
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)

    @staticmethod
    def _max_drawdown(pnls: list[float]) -> float:
        equity = 0.0
        peak = 0.0
        drawdown = 0.0
        for pnl in pnls:
            equity += float(pnl)
            peak = max(peak, equity)
            drawdown = max(drawdown, peak - equity)
        return drawdown

    @staticmethod
    def _empty_strategy() -> dict[str, Any]:
        return {
            "trades": 0,
            "wins": 0,
            "net_pnl": 0.0,
            "gross_profit": 0.0,
            "gross_loss": 0.0,
            "session_pnl": {},
            "pnl_path": [],
            "capital_floor": None,
            "largest_loss": 0.0,
            "last_trade": None,
        }
