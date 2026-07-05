"""
TradingBrain
Risk - Drawdown Tracker

Tracks the equity high-water mark and the running drawdown, and answers the
single question the risk engine cares about: has the configured maximum
drawdown been breached?

Author: TradingBrain
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class DrawdownTracker:
    """Stateful peak-to-trough equity drawdown tracker."""

    max_drawdown_fraction: float = 0.10
    peak_equity: float = 0.0
    trough_equity: float = 0.0
    max_observed_drawdown: float = 0.0
    _initialized: bool = field(default=False, repr=False)

    def update(self, equity: float) -> float:
        """Feed the latest equity; returns the current drawdown fraction."""
        if not self._initialized:
            self.peak_equity = equity
            self.trough_equity = equity
            self._initialized = True

        if equity > self.peak_equity:
            self.peak_equity = equity
            self.trough_equity = equity
        else:
            self.trough_equity = min(self.trough_equity, equity)

        current = self.current_drawdown_fraction()
        self.max_observed_drawdown = max(self.max_observed_drawdown, current)
        return current

    def current_drawdown(self) -> float:
        return max(0.0, self.peak_equity - self.trough_equity)

    def current_drawdown_fraction(self) -> float:
        if self.peak_equity <= 0:
            return 0.0
        return self.current_drawdown() / self.peak_equity

    def is_breached(self) -> bool:
        return self.current_drawdown_fraction() >= self.max_drawdown_fraction

    def reset(self) -> None:
        self.peak_equity = 0.0
        self.trough_equity = 0.0
        self.max_observed_drawdown = 0.0
        self._initialized = False
