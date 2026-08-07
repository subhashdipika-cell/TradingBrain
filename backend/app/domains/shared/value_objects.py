"""
TradingBrain
Shared Value Objects

Immutable, self-validating quantities reused across domains. Value objects
carry meaning and invariants that bare floats cannot.

Author: TradingBrain
"""

from __future__ import annotations

from dataclasses import dataclass

from app.domains.shared.types import Fraction, Money


@dataclass(frozen=True, slots=True)
class Percentage:
    """A ratio stored as a fraction (``Percentage(0.1)`` == 10%)."""

    fraction: Fraction

    @classmethod
    def from_percent(cls, percent: float) -> "Percentage":
        return cls(percent / 100.0)

    @property
    def as_percent(self) -> float:
        return self.fraction * 100.0

    def of(self, amount: Money) -> Money:
        """Apply this percentage to a monetary amount."""
        return amount * self.fraction

    def __str__(self) -> str:  # pragma: no cover - display helper
        return f"{self.as_percent:.2f}%"


@dataclass(frozen=True, slots=True)
class PriceRange:
    """A validated low/high price band."""

    low: float
    high: float

    def __post_init__(self) -> None:
        if self.low > self.high:
            raise ValueError(f"PriceRange low ({self.low}) exceeds high ({self.high}).")

    def contains(self, price: float) -> bool:
        return self.low <= price <= self.high

    @property
    def width(self) -> float:
        return self.high - self.low

    @property
    def mid(self) -> float:
        return (self.low + self.high) / 2.0
