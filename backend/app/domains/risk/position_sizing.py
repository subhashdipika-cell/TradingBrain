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


@dataclass(frozen=True, slots=True)
class SizingResult:
    lots: int
    units: int
    capital_used: float
    reason: str

    @property
    def is_tradable(self) -> bool:
        return self.lots > 0


class PositionSizer:
    """Computes lot sizes from capital and risk parameters."""

    def __init__(self, *, default_margin_pct: float = 0.12) -> None:
        # Approximate SPAN+exposure margin as a fraction of notional. The live
        # broker margin API replaces this estimate in production.
        self._default_margin_pct = default_margin_pct

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
