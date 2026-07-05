"""
TradingBrain
Signal Contract
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.domains.shared.enums import (
    OrderSide,
    PositionSide,
    SignalType,
)


@dataclass(slots=True)
class Signal:
    """
    Standard signal produced by every strategy.
    """

    # Strategy Information
    strategy: str

    # Instrument
    symbol: str

    # Signal
    signal_type: SignalType
    side: OrderSide
    position_side: PositionSide

    # Price Levels
    entry_price: float | None = None
    stop_loss: float | None = None
    take_profit: float | None = None

    # Risk
    requested_risk: float = 0.0

    # Confidence
    confidence: float = 0.0
    score: float = 0.0

    # Description
    reason: str = ""

    # Extension
    tags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def is_entry(self) -> bool:
        return self.signal_type in (
            SignalType.BUY,
            SignalType.SELL,
        )

    @property
    def is_exit(self) -> bool:
        return self.signal_type == SignalType.EXIT

    @property
    def is_hold(self) -> bool:
        return self.signal_type == SignalType.HOLD