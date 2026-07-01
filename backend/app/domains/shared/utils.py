"""
TradingBrain
Shared Utilities

Small, dependency-free helpers used across domains. Anything heavier
(indicators, pricing) lives in its own domain module.

Author: TradingBrain
"""

from __future__ import annotations

import math

from app.domains.shared.types import Fraction, Price


def clamp(value: float, low: float, high: float) -> float:
    """Constrain ``value`` to the inclusive ``[low, high]`` range."""
    return max(low, min(high, value))


def safe_div(numerator: float, denominator: float, default: float = 0.0) -> float:
    """Divide guarding against zero/NaN denominators."""
    if denominator == 0 or math.isnan(denominator):
        return default
    return numerator / denominator


def round_to_tick(price: Price, tick_size: float = 0.05) -> Price:
    """Round ``price`` to the nearest exchange tick (default 0.05 for NSE)."""
    if tick_size <= 0:
        return price
    return round(round(price / tick_size) * tick_size, 2)


def round_to_step(value: float, step: float) -> float:
    """Round ``value`` to the nearest multiple of ``step`` (e.g. strike step)."""
    if step <= 0:
        return value
    return round(value / step) * step


def pct(part: float, whole: float, default: float = 0.0) -> Fraction:
    """Return ``part / whole`` as a fraction, guarding against zero."""
    return safe_div(part, whole, default)


def basis_points(fraction: Fraction) -> float:
    """Convert a fraction (0.01) to basis points (100)."""
    return fraction * 10_000.0


def is_close(a: float, b: float, tol: float = 1e-9) -> bool:
    """Tolerant float equality."""
    return abs(a - b) <= tol
