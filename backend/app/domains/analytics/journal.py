"""
TradingBrain
Analytics - Trade Journal

Records what the engine did: every closed trade (round-trip), the equity
curve sampled over time, and freeform events. The journal is the raw material
that statistics, performance and reports are computed from.

Author: TradingBrain
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True, slots=True)
class TradeRecord:
    """A completed round-trip trade."""

    strategy: str
    symbol: str
    structure: str  # e.g. "SHORT_STRADDLE"
    entry_time: datetime
    exit_time: datetime
    entry_value: float  # premium collected / paid at entry (rupees)
    exit_value: float  # premium paid / collected at exit (rupees)
    pnl: float  # net realized PnL (rupees, incl. costs)
    commission: float
    exit_reason: str
    lots: int

    @property
    def is_win(self) -> bool:
        return self.pnl > 0

    @property
    def duration_minutes(self) -> float:
        return (self.exit_time - self.entry_time).total_seconds() / 60.0


@dataclass(frozen=True, slots=True)
class EquityPoint:
    timestamp: datetime
    equity: float


@dataclass(slots=True)
class TradeJournal:
    """Append-only record of trades, equity samples and events."""

    trades: list[TradeRecord] = field(default_factory=list)
    equity_curve: list[EquityPoint] = field(default_factory=list)
    events: list[tuple[datetime, str]] = field(default_factory=list)

    def record_trade(self, trade: TradeRecord) -> None:
        self.trades.append(trade)

    def record_equity(self, timestamp: datetime, equity: float) -> None:
        self.equity_curve.append(EquityPoint(timestamp, equity))

    def record_event(self, timestamp: datetime, message: str) -> None:
        self.events.append((timestamp, message))

    # Convenience views
    def pnls(self) -> list[float]:
        return [t.pnl for t in self.trades]

    def equity_values(self) -> list[float]:
        return [p.equity for p in self.equity_curve]

    @property
    def trade_count(self) -> int:
        return len(self.trades)
