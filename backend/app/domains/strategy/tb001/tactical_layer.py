"""
TradingBrain

TB001 - Tactical Layer
"""

from __future__ import annotations

from app.domains.strategy.contracts.context import MarketContext
from app.domains.strategy.contracts.signal import Signal
from app.domains.strategy.tb001.configuration import TB001Configuration


class TacticalLayer:
    """
    Tactical adjustments for TB001.

    This layer is only activated when the Core Layer
    requires additional action.

    Future responsibilities:
        - Momentum option buying
        - Gamma scalping
        - Mean reversion entries
        - Position pyramiding
        - Tactical exits

    It never creates the primary trade.
    It only enhances or protects it.
    """

    def __init__(self, config: TB001Configuration) -> None:
        self._config = config

    def evaluate(
        self,
        context: MarketContext,
        signal: Signal | None,
    ) -> Signal | None:
        """
        Evaluate tactical opportunities.

        Phase 1:
            Pass-through.

        Future phases will modify or augment
        the incoming signal.
        """

        if signal is None:
            return None

        if self.should_activate(context):
            return signal

        return signal

    def should_activate(
        self,
        context: MarketContext,
    ) -> bool:
        """
        Decide whether the tactical layer should activate.

        Future activation examples:
            - Momentum breakout
            - Delta imbalance
            - Gamma expansion
            - Strong trend day
            - High volatility

        Phase 1:
            Disabled.
        """
        return False

    def should_buy_options(
        self,
        context: MarketContext,
    ) -> bool:
        """
        Placeholder for directional option buying.
        """
        return False

    def should_gamma_scalp(
        self,
        context: MarketContext,
    ) -> bool:
        """
        Placeholder for gamma scalping logic.
        """
        return False

    def should_pyramid(
        self,
        context: MarketContext,
    ) -> bool:
        """
        Placeholder for pyramiding logic.
        """
        return False

    def should_reduce_position(
        self,
        context: MarketContext,
    ) -> bool:
        """
        Placeholder for tactical position reduction.
        """
        return False