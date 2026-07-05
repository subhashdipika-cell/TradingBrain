"""
TradingBrain

TB008 - Payoff Engine

Payoff analysis is central to TB008 (unlike TB001). A calendar spread's payoff
depends on the *evaluation date*: near-expiry legs decay to intrinsic value
while the far-expiry hedges still carry time value. This engine evaluates the
structure at the NEAR expiry across a grid of underlying prices and reports the
metrics the strategy and risk layers reason about.

Author: TradingBrain
"""

from __future__ import annotations

from datetime import date

from app.domains.market.greeks import black_scholes
from app.domains.strategy.tb008.models import (
    CalendarLeg,
    CalendarStructure,
    PayoffProfile,
)
from app.domains.shared.enums import OptionRight

_DAYS_PER_YEAR = 365.0


class PayoffEngine:
    """Evaluates a :class:`CalendarStructure` at the near expiry."""

    def __init__(
        self,
        *,
        rate: float = 0.065,
        margin_pct: float = 0.04,
        grid_width: float = 0.06,
        grid_points: int = 121,
    ) -> None:
        self._rate = rate
        self._margin_pct = margin_pct
        self._grid_width = grid_width
        self._grid_points = grid_points

    # ------------------------------------------------------------------
    def analyze(
        self, structure: CalendarStructure, *, band_pct: float = 0.02
    ) -> PayoffProfile:
        spot = structure.spot
        lot_size = structure.lot_size
        far_tte = self._far_remaining_years(structure.near_expiry, structure.far_expiry)

        prices = self._grid(spot)
        pnls = [self._pnl_at(structure, s, far_tte, lot_size) for s in prices]

        max_profit = max(pnls)
        max_loss = min(pnls)
        breakevens = self._breakevens(prices, pnls)
        profit_low, profit_high = self._profit_band(prices, pnls)
        coverage = (
            (profit_high - profit_low) / spot
            if profit_low is not None and profit_high is not None
            else 0.0
        )

        sold_lots = max((leg.lots for leg in structure.sold_legs()), default=0)
        margin = max(
            abs(max_loss),
            spot * lot_size * sold_lots * self._margin_pct,
        )
        efficiency = max_profit / margin if margin > 0 else 0.0
        smoothness = self._smoothness(prices, pnls, spot, band_pct, margin)

        return PayoffProfile(
            max_profit=max_profit,
            max_loss=max_loss,
            breakevens=breakevens,
            profit_low=profit_low,
            profit_high=profit_high,
            range_coverage_pct=coverage,
            margin=margin,
            margin_efficiency=efficiency,
            mtm_smoothness=smoothness,
            net_credit=structure.net_credit_per_unit() * lot_size,
        )

    # ------------------------------------------------------------------
    def _pnl_at(
        self, structure: CalendarStructure, spot: float, far_tte: float, lot_size: int
    ) -> float:
        total = 0.0
        for leg in structure.legs:
            value = self._leg_value(leg, spot, far_tte, structure.implied_vol)
            total += leg.signed_lots * (value - leg.price) * lot_size
        return total

    def _leg_value(
        self, leg: CalendarLeg, spot: float, far_tte: float, iv: float
    ) -> float:
        if leg.expiry_bucket == "near":
            # Near legs are at (their) expiry -> intrinsic value.
            if leg.right is OptionRight.CALL:
                return max(spot - leg.strike, 0.0)
            return max(leg.strike - spot, 0.0)
        # Far legs still carry time value at the near expiry.
        return black_scholes(
            right=leg.right,
            spot=spot,
            strike=leg.strike,
            time_to_expiry=max(far_tte, 1e-6),
            volatility=max(iv, 1e-4),
            rate=self._rate,
        ).price

    # ------------------------------------------------------------------
    def _grid(self, spot: float) -> list[float]:
        lo = spot * (1.0 - self._grid_width)
        hi = spot * (1.0 + self._grid_width)
        step = (hi - lo) / (self._grid_points - 1)
        return [lo + i * step for i in range(self._grid_points)]

    @staticmethod
    def _breakevens(prices: list[float], pnls: list[float]) -> tuple[float, ...]:
        out: list[float] = []
        for i in range(1, len(pnls)):
            a, b = pnls[i - 1], pnls[i]
            if (a <= 0 < b) or (a >= 0 > b):
                # linear interpolation of the zero crossing
                t = a / (a - b) if a != b else 0.0
                out.append(prices[i - 1] + t * (prices[i] - prices[i - 1]))
        return tuple(out)

    @staticmethod
    def _profit_band(
        prices: list[float], pnls: list[float]
    ) -> tuple[float | None, float | None]:
        profitable = [p for p, pnl in zip(prices, pnls) if pnl >= 0]
        if not profitable:
            return None, None
        return min(profitable), max(profitable)

    @staticmethod
    def _smoothness(
        prices: list[float],
        pnls: list[float],
        spot: float,
        band_pct: float,
        margin: float,
    ) -> float:
        lo, hi = spot * (1.0 - band_pct), spot * (1.0 + band_pct)
        band = [pnl for p, pnl in zip(prices, pnls) if lo <= p <= hi]
        if not band or margin <= 0:
            return 0.0
        swing = max(band) - min(band)
        return max(0.0, 1.0 - swing / margin)

    @staticmethod
    def _far_remaining_years(near_expiry: date, far_expiry: date) -> float:
        return max((far_expiry - near_expiry).days, 0) / _DAYS_PER_YEAR
