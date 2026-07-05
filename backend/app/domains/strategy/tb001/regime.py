"""
TradingBrain

TB001 - Market Regime Detection
"""

from __future__ import annotations

from app.domains.shared.enums import (
    MarketRegime,
    TrendDirection,
    VolatilityRegime,
)
from app.domains.strategy.contracts.context import MarketContext


class RegimeDetector:
    """
    Determines the current market regime.

    This implementation is intentionally simple.
    Rules will be enhanced as TB001 evolves.
    """

    def detect(self, context: MarketContext) -> MarketRegime:
        """
        Determine the current market regime.
        """

        if context.volatility_regime == VolatilityRegime.EXTREME:
            return MarketRegime.VOLATILE

        if (
            context.trend == TrendDirection.BULLISH
            and context.adx >= 25
        ):
            return MarketRegime.TRENDING

        if (
            context.trend == TrendDirection.BEARISH
            and context.adx >= 25
        ):
            return MarketRegime.TRENDING

        if context.adx < 20:
            return MarketRegime.RANGING

        return MarketRegime.UNKNOWN

    def is_trending(self, context: MarketContext) -> bool:
        return self.detect(context) == MarketRegime.TRENDING

    def is_ranging(self, context: MarketContext) -> bool:
        return self.detect(context) == MarketRegime.RANGING

    def is_volatile(self, context: MarketContext) -> bool:
        return self.detect(context) == MarketRegime.VOLATILE