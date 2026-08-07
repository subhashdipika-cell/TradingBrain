"""
TradingBrain

TB008 - Adaptive Calendar Spread Engine - Models
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum

from app.domains.shared.enums import OptionRight


class VixLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class VixTrend(str, Enum):
    EXPANDING = "EXPANDING"
    CONTRACTING = "CONTRACTING"
    STABLE = "STABLE"


@dataclass(frozen=True, slots=True)
class VixAssessment:
    """Volatility-regime read used to gate and shape the structure."""

    vix: float
    level: VixLevel
    trend: VixTrend
    favorable: bool  # True only when it is safe to deploy (low vol)
    expansion_risk: bool  # vol so compressed it is likely to expand


@dataclass(frozen=True, slots=True)
class CalendarLeg:
    """One leg of the calendar structure."""

    right: OptionRight
    strike: float
    side: str  # "BUY" or "SELL"
    expiry_bucket: str  # "near" or "far"
    lots: int
    price: float  # entry premium per unit
    delta: float

    @property
    def signed_lots(self) -> int:
        return self.lots if self.side == "BUY" else -self.lots


@dataclass(slots=True)
class CalendarStructure:
    """The full TB008 double-calendar (short near strangle + far ratio hedge)."""

    symbol: str
    spot: float
    lot_size: int
    near_expiry: date
    far_expiry: date
    implied_vol: float
    legs: list[CalendarLeg] = field(default_factory=list)

    def sold_legs(self) -> list[CalendarLeg]:
        return [leg for leg in self.legs if leg.side == "SELL"]

    def hedge_legs(self) -> list[CalendarLeg]:
        return [leg for leg in self.legs if leg.side == "BUY"]

    def net_credit_per_unit(self) -> float:
        """Premium collected minus premium paid, per unit (can be negative)."""
        credit = sum(leg.price * leg.lots for leg in self.sold_legs())
        debit = sum(leg.price * leg.lots for leg in self.hedge_legs())
        return credit - debit


@dataclass(frozen=True, slots=True)
class PayoffProfile:
    """Payoff analysis evaluated at the near expiry across the price grid."""

    max_profit: float
    max_loss: float
    breakevens: tuple[float, ...]
    profit_low: float | None  # lower edge of the profitable band
    profit_high: float | None  # upper edge of the profitable band
    range_coverage_pct: float  # profitable band width / spot
    margin: float
    margin_efficiency: float  # max_profit / margin
    mtm_smoothness: float  # 0..1, higher = flatter P&L across the weekly range
    net_credit: float
