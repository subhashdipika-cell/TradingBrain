"""
TradingBrain
Intelligence - Regime Detection

A platform-level market-regime classifier, separate from any single strategy.
The default implementation is rule-based (volatility + trend heuristics); a
learned classifier can implement the same :class:`RegimeClassifier` interface
later without touching callers.

Author: TradingBrain
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.domains.shared.enums import (
    MarketRegime,
    TrendDirection,
    VolatilityRegime,
)
from app.domains.strategy.contracts.context import MarketContext


class RegimeClassifier(ABC):
    """Classifies the prevailing market regime from a MarketContext."""

    @abstractmethod
    def classify(self, context: MarketContext) -> MarketRegime:
        raise NotImplementedError


class RuleBasedRegimeClassifier(RegimeClassifier):
    """Heuristic regime classifier driven by volatility, ADX and trend."""

    def __init__(self, *, adx_trend: float = 25.0, adx_range: float = 20.0) -> None:
        self._adx_trend = adx_trend
        self._adx_range = adx_range

    def classify(self, context: MarketContext) -> MarketRegime:
        if context.volatility_regime in (
            VolatilityRegime.EXTREME,
            VolatilityRegime.HIGH,
        ):
            return MarketRegime.VOLATILE

        if context.adx >= self._adx_trend and context.trend in (
            TrendDirection.BULLISH,
            TrendDirection.BEARISH,
        ):
            return MarketRegime.TRENDING

        if context.adx <= self._adx_range:
            return MarketRegime.RANGING

        return MarketRegime.UNKNOWN
