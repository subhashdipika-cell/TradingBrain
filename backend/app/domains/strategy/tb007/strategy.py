"""
TradingBrain

TB007 - Convexity Buy Strategy

A long-volatility option buyer: buys a cheap, defined-risk long option when IV
is low AND price is coiled in a Bollinger squeeze, then rides the expansion.
The deliberate long-vol mirror of the short-premium book (TB001/TB003-006).
"""

from __future__ import annotations

from app.domains.strategy.contracts.context import MarketContext
from app.domains.strategy.contracts.signal import Signal
from app.domains.strategy.contracts.strategy import BaseStrategy
from app.domains.strategy.tb007.configuration import TB007Configuration
from app.domains.strategy.tb007.core_layer import CoreLayer


class TB007Strategy(BaseStrategy):
    """TB007 - Convexity Buy (low-IV squeeze-break long option)."""

    name = "TB007"
    version = "1.0.0"
    description = "Convexity Buy - low-IV squeeze-break long option (long vol)"

    def __init__(self) -> None:
        super().__init__()
        self.configuration = TB007Configuration()
        self.core_layer = CoreLayer(self.configuration)

    def initialize(self) -> None:
        self.enabled = True

    def pre_market(self, context: MarketContext) -> None:
        return

    def generate_signal(self, context: MarketContext) -> Signal | None:
        return self.core_layer.evaluate(context)

    def manage_position(self, context: MarketContext) -> Signal | None:
        return None

    def manage_risk(self, context: MarketContext) -> None:
        return

    def post_market(self, context: MarketContext) -> None:
        self.reset()

    def reset(self) -> None:
        self.core_layer.reset()
