"""Point-in-time realized-volatility helpers for strategy eligibility gates."""

from __future__ import annotations

import math
from statistics import stdev


def annualized_realized_volatility(
    candles: list,
    *,
    bar_minutes: int,
    lookback_returns: int = 60,
    min_returns: int = 20,
) -> float | None:
    """Estimate close-to-close RV from completed intraday candles only.

    Overnight/session gaps are excluded because the intraday annualisation
    factor would otherwise treat a multi-hour gap as one short bar. Callers are
    responsible for excluding the currently forming candle.
    """
    if bar_minutes <= 0:
        raise ValueError("bar_minutes must be positive")
    if min_returns < 2:
        raise ValueError("min_returns must be at least 2")

    returns: list[float] = []
    max_gap_seconds = bar_minutes * 60 * 1.5
    for previous, current in zip(candles, candles[1:]):
        elapsed = (current.timestamp - previous.timestamp).total_seconds()
        if elapsed <= 0 or elapsed > max_gap_seconds:
            continue
        if previous.close <= 0 or current.close <= 0:
            continue
        returns.append(math.log(current.close / previous.close))

    returns = returns[-lookback_returns:]
    if len(returns) < min_returns:
        return None

    bars_per_year = 252.0 * (375.0 / bar_minutes)
    return stdev(returns) * math.sqrt(bars_per_year)
