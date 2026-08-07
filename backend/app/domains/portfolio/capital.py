"""
TradingBrain
Portfolio - Capital

Tracks account capital: starting capital, realized cash flows and the
current equity high-water mark (used by drawdown control).

Author: TradingBrain
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class Capital:
    """Account capital and equity tracking."""

    starting_capital: float
    realized_pnl: float = 0.0
    high_water_mark: float = 0.0

    def __post_init__(self) -> None:
        if self.starting_capital <= 0:
            raise ValueError("starting_capital must be positive.")
        if self.high_water_mark == 0.0:
            self.high_water_mark = self.starting_capital

    def equity(self, unrealized_pnl: float = 0.0) -> float:
        """Total equity = starting capital + realized + unrealized PnL."""
        return self.starting_capital + self.realized_pnl + unrealized_pnl

    def book_realized(self, amount: float) -> None:
        self.realized_pnl += amount

    def update_high_water_mark(self, unrealized_pnl: float = 0.0) -> None:
        self.high_water_mark = max(self.high_water_mark, self.equity(unrealized_pnl))

    def drawdown(self, unrealized_pnl: float = 0.0) -> float:
        """Absolute drawdown from the high-water mark (>= 0)."""
        return max(0.0, self.high_water_mark - self.equity(unrealized_pnl))

    def drawdown_fraction(self, unrealized_pnl: float = 0.0) -> float:
        """Drawdown as a fraction of the high-water mark."""
        if self.high_water_mark <= 0:
            return 0.0
        return self.drawdown(unrealized_pnl) / self.high_water_mark

    def reset_realized(self) -> None:
        """Reset realized PnL for a new accounting period (keeps HWM)."""
        self.realized_pnl = 0.0
