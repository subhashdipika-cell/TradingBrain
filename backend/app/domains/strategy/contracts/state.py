"""
TradingBrain
Strategy State Contract
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from app.domains.shared.enums import StrategyState


@dataclass(slots=True)
class State:
    """
    Runtime state of a strategy.

    This object is maintained by the Strategy Manager and can be
    updated by the strategy during execution.
    """

    state: StrategyState = StrategyState.INITIALIZED

    initialized: bool = False

    active: bool = False

    in_position: bool = False

    entry_time: datetime | None = None

    exit_time: datetime | None = None

    last_signal_time: datetime | None = None

    trade_count: int = 0

    win_count: int = 0

    loss_count: int = 0

    pnl: float = 0.0

    metadata: dict[str, Any] = field(default_factory=dict)

    def reset(self) -> None:
        """
        Reset state for a new trading session.
        """
        self.state = StrategyState.INITIALIZED
        self.initialized = False
        self.active = False
        self.in_position = False
        self.entry_time = None
        self.exit_time = None
        self.last_signal_time = None
        self.trade_count = 0
        self.win_count = 0
        self.loss_count = 0
        self.pnl = 0.0
        self.metadata.clear()