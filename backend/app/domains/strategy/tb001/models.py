"""
TradingBrain

TB001 - Strategy Models
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class PositionStatus(str, Enum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"
    PENDING = "PENDING"


@dataclass(slots=True)
class StrategyPosition:
    """
    Represents the current strategy position.
    """

    symbol: str

    status: PositionStatus = PositionStatus.CLOSED

    entry_time: datetime | None = None

    exit_time: datetime | None = None

    entry_price: float = 0.0

    exit_price: float = 0.0

    quantity: int = 0

    pnl: float = 0.0

    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class StrategyStatistics:
    """
    Runtime statistics for TB001.
    """

    total_trades: int = 0

    winning_trades: int = 0

    losing_trades: int = 0

    gross_profit: float = 0.0

    gross_loss: float = 0.0

    net_profit: float = 0.0

    max_drawdown: float = 0.0

    win_rate: float = 0.0

    profit_factor: float = 0.0

    expectancy: float = 0.0