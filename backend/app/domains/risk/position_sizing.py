"""
TradingBrain
Risk - Position Sizing

Translates a capital allocation / risk budget into a concrete number of lots.
Two sizing modes are supported:

- **Margin-based** (for premium selling like short straddles): how many lots
  fit inside the allocated capital given an estimated margin per lot.
- **Risk-based** (for defined-risk directional trades): how many lots keep
  the loss at the stop within the per-trade risk budget.

Author: TradingBrain
"""

from __future__ import annotations

from dataclasses import dataclass
from math import floor


INDEX_LOT_SIZES: dict[str, int] = {
    "NIFTY": 65,
    "NIFTY50": 65,
    "BANKNIFTY": 30,
    "FINNIFTY": 60,
}

DEFAULT_MAX_LOTS = 20


@dataclass(frozen=True, slots=True)
class SizingResult:
    lots: int
    units: int
    capital_used: float
    reason: str

    @property
    def is_tradable(self) -> bool:
        return self.lots > 0


@dataclass(frozen=True, slots=True)
class SpreadSizingResult:
    """Risk-based result for a defined-risk credit spread structure."""

    safe_lot_count: int
    max_possible_loss: float
    is_trade_allowed: bool
    spread_width: float
    adjusted_long_strike: float | None = None
    reason: str = ""


class PositionSizer:
    """Computes lot sizes from capital and risk parameters."""

    def __init__(
        self,
        *,
        default_margin_pct: float = 0.12,
        risk_fraction: float = 0.01,
        max_lots_per_trade: int = DEFAULT_MAX_LOTS,
        symbol_lot_sizes: dict[str, int] | None = None,
    ) -> None:
        # Approximate SPAN+exposure margin as a fraction of notional. The live
        # broker margin API replaces this estimate in production.
        self._default_margin_pct = default_margin_pct
        if not 0.0 < risk_fraction <= 0.015:
            raise ValueError("risk_fraction must be within (0, 0.015].")
        if max_lots_per_trade <= 0:
            raise ValueError("max_lots_per_trade must be positive.")
        self._risk_fraction = risk_fraction
        self._max_lots_per_trade = max_lots_per_trade
        self._symbol_lot_sizes = {
            **INDEX_LOT_SIZES,
            **(symbol_lot_sizes or {}),
        }

    def lot_size_for(self, symbol: str, fallback: int | None = None) -> int:
        """Return the configured lot size, using the broker contract as fallback."""
        key = symbol.upper().replace(" ", "")
        if key in self._symbol_lot_sizes:
            return self._symbol_lot_sizes[key]
        if fallback is not None and fallback > 0:
            return fallback
        raise ValueError(f"No lot size configured for symbol {symbol!r}.")

    def size_credit_spread(
        self,
        *,
        account_balance: float,
        strategy_type: str,
        short_strike: float,
        long_strike: float,
        net_credit: float,
        symbol: str,
        lot_size: int | None = None,
        requested_lots: int | None = None,
    ) -> SpreadSizingResult:
        """Size a credit spread using fixed-fractional maximum loss.

        ``net_credit`` is the total structure credit per underlying point. For
        an Iron Condor, callers pass the widest wing as ``long_strike`` and
        ``short_strike``. The optional requested lot count can only reduce the
        safe size; it can never override risk limits.
        """
        if account_balance <= 0:
            return SpreadSizingResult(0, 0.0, False, 0.0, reason="invalid account balance")
        width = abs(float(long_strike) - float(short_strike))
        if width <= 0 or net_credit < 0:
            return SpreadSizingResult(0, 0.0, False, width, reason="invalid spread geometry")

        multiplier = lot_size or self.lot_size_for(symbol)
        risk_per_unit = max(width - float(net_credit), 0.0)
        risk_per_lot = risk_per_unit * multiplier
        if risk_per_lot <= 0:
            return SpreadSizingResult(0, 0.0, False, width, reason="credit exceeds spread width")

        risk_budget = account_balance * self._risk_fraction
        safe_lots = floor(risk_budget / risk_per_lot)
        safe_lots = min(safe_lots, self._max_lots_per_trade)
        if requested_lots is not None:
            safe_lots = min(safe_lots, max(0, requested_lots))
        if safe_lots <= 0:
            return SpreadSizingResult(
                0, 0.0, False, width, reason="risk budget below one lot"
            )
        return SpreadSizingResult(
            safe_lot_count=safe_lots,
            max_possible_loss=risk_per_lot * safe_lots,
            is_trade_allowed=True,
            spread_width=width,
            reason=f"{strategy_type} fixed-fractional sizing",
        )

    def max_allowed_spread_width(
        self, *, account_balance: float, net_credit: float, symbol: str, lot_size: int | None = None
    ) -> float:
        """Maximum width that keeps one lot within the configured risk budget."""
        multiplier = lot_size or self.lot_size_for(symbol)
        return account_balance * self._risk_fraction / multiplier + net_credit

    def adjust_hedge_strike(
        self,
        *,
        account_balance: float,
        short_strike: float,
        long_strike: float,
        net_credit: float,
        symbol: str,
        lot_size: int | None = None,
    ) -> float:
        """Move a protective long strike closer when the requested wing is too wide."""
        max_width = self.max_allowed_spread_width(
            account_balance=account_balance,
            net_credit=net_credit,
            symbol=symbol,
            lot_size=lot_size,
        )
        width = abs(long_strike - short_strike)
        if width <= max_width:
            return long_strike
        direction = 1.0 if long_strike > short_strike else -1.0
        return short_strike + direction * max_width

    def margin_per_lot(
        self, *, spot: float, lot_size: int, margin_pct: float | None = None
    ) -> float:
        pct = self._default_margin_pct if margin_pct is None else margin_pct
        return spot * lot_size * pct

    def size_for_premium_selling(
        self,
        *,
        capital: float,
        allocation_fraction: float,
        spot: float,
        lot_size: int,
        margin_pct: float | None = None,
    ) -> SizingResult:
        """Lots that fit within ``capital * allocation_fraction`` of margin."""
        budget = capital * allocation_fraction
        per_lot = self.margin_per_lot(
            spot=spot, lot_size=lot_size, margin_pct=margin_pct
        )
        if per_lot <= 0:
            return SizingResult(0, 0, 0.0, "invalid margin per lot")

        lots = int(budget // per_lot)
        if lots <= 0:
            return SizingResult(0, 0, 0.0, "insufficient capital for one lot")
        return SizingResult(
            lots=lots,
            units=lots * lot_size,
            capital_used=lots * per_lot,
            reason="margin-based sizing",
        )

    def size_for_margin(
        self,
        *,
        capital: float,
        allocation_fraction: float,
        margin_per_lot: float,
        lot_size: int,
    ) -> SizingResult:
        """
        Generic margin-based sizing given a precomputed margin per lot. Used
        for defined-risk structures (Iron Fly) whose margin is the max loss,
        far below naked SPAN - so far more lots fit the same budget.
        """
        if margin_per_lot <= 0:
            return SizingResult(0, 0, 0.0, "invalid margin per lot")
        budget = capital * allocation_fraction
        lots = int(budget // margin_per_lot)
        if lots <= 0:
            return SizingResult(0, 0, 0.0, "insufficient capital for one lot")
        return SizingResult(
            lots=lots,
            units=lots * lot_size,
            capital_used=lots * margin_per_lot,
            reason="defined-risk margin sizing",
        )

    def size_by_risk(
        self,
        *,
        capital: float,
        risk_fraction: float,
        stop_loss_points: float,
        lot_size: int,
    ) -> SizingResult:
        """Lots so that loss at the stop stays within the risk budget."""
        if stop_loss_points <= 0:
            return SizingResult(0, 0, 0.0, "invalid stop distance")
        risk_amount = capital * risk_fraction
        risk_per_lot = stop_loss_points * lot_size
        lots = int(risk_amount // risk_per_lot)
        if lots <= 0:
            return SizingResult(0, 0, 0.0, "risk budget below one lot")
        return SizingResult(
            lots=lots,
            units=lots * lot_size,
            capital_used=risk_amount,
            reason="risk-based sizing",
        )
