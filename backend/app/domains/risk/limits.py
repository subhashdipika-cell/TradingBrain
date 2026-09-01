"""
TradingBrain
Risk - Limits

Declarative risk limits applied platform-wide, independent of any single
strategy. The Risk Engine reads these to vet signals and to decide when the
kill switch must trip.

All fractions are of starting capital unless noted.

Author: TradingBrain
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RiskLimits:
    """Platform-level risk limits."""

    # Loss controls (fractions of capital)
    max_daily_loss: float = 0.10
    max_drawdown: float = 0.10
    max_position_risk: float = 0.02

    # Capital deployment
    max_capital_per_trade: float = 0.33
    max_total_exposure: float = 1.0

    # Greeks ceilings (absolute, in underlying units across the book)
    max_net_delta: float = 5_000.0
    max_net_gamma: float = 500.0

    # Activity controls
    max_open_positions: int = 8
    max_trades_per_day: int = 10

    def __post_init__(self) -> None:
        for name, value in (
            ("max_daily_loss", self.max_daily_loss),
            ("max_drawdown", self.max_drawdown),
            ("max_position_risk", self.max_position_risk),
            ("max_capital_per_trade", self.max_capital_per_trade),
            ("max_total_exposure", self.max_total_exposure),
        ):
            if not 0.0 < value <= 1.0:
                raise ValueError(f"{name} must be within (0, 1], got {value}.")
        if self.max_open_positions <= 0:
            raise ValueError("max_open_positions must be positive.")
        if self.max_trades_per_day <= 0:
            raise ValueError("max_trades_per_day must be positive.")
