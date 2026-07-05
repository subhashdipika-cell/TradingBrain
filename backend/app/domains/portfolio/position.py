"""
TradingBrain
Portfolio - Position

A single open position in one instrument (option leg or underlying).
Quantity is signed: positive = long, negative = short. PnL is computed in
rupees using the contract multiplier (lot size for options).

Author: TradingBrain
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from app.domains.shared.enums import OptionRight, PositionSide


@dataclass(slots=True)
class Position:
    """An open position in one tradable instrument."""

    symbol: str
    instrument: str  # tradingsymbol, e.g. "NIFTY25000CE"
    quantity: int  # signed: + long, - short (in units, not lots)
    avg_price: float
    multiplier: int = 1  # lot size for options, 1 for cash
    opened_at: datetime | None = None

    # Option metadata (None for non-option instruments)
    right: OptionRight | None = None
    strike: float | None = None

    # Marked each tick by the portfolio
    last_price: float = 0.0

    # Realized PnL accumulated from quantity reductions on this instrument
    realized_pnl: float = 0.0

    metadata: dict[str, object] = field(default_factory=dict)

    # ------------------------------------------------------------------
    # Derived
    # ------------------------------------------------------------------
    @property
    def is_open(self) -> bool:
        return self.quantity != 0

    @property
    def side(self) -> PositionSide:
        if self.quantity > 0:
            return PositionSide.LONG
        if self.quantity < 0:
            return PositionSide.SHORT
        return PositionSide.FLAT

    @property
    def is_option(self) -> bool:
        return self.right is not None

    def market_value(self, price: float | None = None) -> float:
        """Signed mark-to-market value in rupees."""
        px = self.last_price if price is None else price
        return self.quantity * px * self.multiplier

    def unrealized_pnl(self, price: float | None = None) -> float:
        """Unrealized PnL in rupees at ``price`` (or last marked price)."""
        px = self.last_price if price is None else price
        return (px - self.avg_price) * self.quantity * self.multiplier

    def total_pnl(self, price: float | None = None) -> float:
        return self.realized_pnl + self.unrealized_pnl(price)

    # ------------------------------------------------------------------
    # Mutations
    # ------------------------------------------------------------------
    def mark(self, price: float) -> None:
        self.last_price = price

    def apply_fill(self, fill_qty: int, fill_price: float) -> None:
        """
        Apply a signed fill (``fill_qty`` + buy, - sell) to this position,
        updating average price (on increase) or realizing PnL (on decrease).
        """
        if fill_qty == 0:
            return

        same_direction = (self.quantity >= 0 and fill_qty > 0) or (
            self.quantity <= 0 and fill_qty < 0
        )

        if self.quantity == 0 or same_direction:
            # Opening or increasing: weighted-average the entry price.
            total_qty = self.quantity + fill_qty
            self.avg_price = (
                self.avg_price * self.quantity + fill_price * fill_qty
            ) / total_qty
            self.quantity = total_qty
            return

        # Reducing / closing / flipping: realize PnL on the closed portion.
        closing_qty = min(abs(fill_qty), abs(self.quantity))
        direction = 1 if self.quantity > 0 else -1
        self.realized_pnl += (
            (fill_price - self.avg_price) * direction * closing_qty * self.multiplier
        )

        remaining = abs(fill_qty) - closing_qty
        self.quantity += fill_qty

        if self.quantity == 0 and remaining > 0:
            # Position flipped through zero: open the remainder at fill price.
            self.quantity = remaining if fill_qty > 0 else -remaining
            self.avg_price = fill_price
        elif self.quantity == 0:
            self.avg_price = 0.0
