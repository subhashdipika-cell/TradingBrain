"""
TradingBrain
Analytics - Performance Metrics

Equity-curve analytics: total/percentage return, maximum drawdown, and a
(non-annualized and annualized) Sharpe ratio computed from successive equity
samples. Inputs are the equity points recorded by the journal.

Author: TradingBrain
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from app.domains.shared.utils import safe_div


@dataclass(frozen=True, slots=True)
class PerformanceMetrics:
    starting_equity: float = 0.0
    ending_equity: float = 0.0
    net_return: float = 0.0
    return_pct: float = 0.0
    max_drawdown: float = 0.0
    max_drawdown_pct: float = 0.0
    sharpe: float = 0.0
    samples: int = 0


def _max_drawdown(equity: list[float]) -> tuple[float, float]:
    peak = equity[0]
    max_dd = 0.0
    max_dd_pct = 0.0
    for value in equity:
        peak = max(peak, value)
        dd = peak - value
        if dd > max_dd:
            max_dd = dd
            max_dd_pct = safe_div(dd, peak)
    return max_dd, max_dd_pct


def _sharpe(equity: list[float], periods_per_year: float) -> float:
    """Annualized Sharpe from period-over-period equity returns (rf=0)."""
    if len(equity) < 3:
        return 0.0
    returns: list[float] = []
    for prev, curr in zip(equity, equity[1:]):
        if prev != 0:
            returns.append((curr - prev) / prev)
    if len(returns) < 2:
        return 0.0
    mean = sum(returns) / len(returns)
    variance = sum((r - mean) ** 2 for r in returns) / (len(returns) - 1)
    std = math.sqrt(variance)
    if std == 0:
        return 0.0
    return (mean / std) * math.sqrt(periods_per_year)


def compute_performance(
    equity: list[float], *, periods_per_year: float = 252.0
) -> PerformanceMetrics:
    """Compute equity-curve performance metrics."""
    if not equity:
        return PerformanceMetrics()

    start = equity[0]
    end = equity[-1]
    net_return = end - start
    max_dd, max_dd_pct = _max_drawdown(equity)

    return PerformanceMetrics(
        starting_equity=start,
        ending_equity=end,
        net_return=net_return,
        return_pct=safe_div(net_return, start),
        max_drawdown=max_dd,
        max_drawdown_pct=max_dd_pct,
        sharpe=_sharpe(equity, periods_per_year),
        samples=len(equity),
    )
