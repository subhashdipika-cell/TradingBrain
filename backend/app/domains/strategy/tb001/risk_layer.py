"""
TradingBrain

TB001 - Risk Layer
"""

from __future__ import annotations

from app.domains.strategy.contracts.context import MarketContext
from app.domains.strategy.contracts.signal import Signal
from app.domains.strategy.tb001.configuration import TB001Configuration


class RiskLayer:
    """
    Strategy-specific risk validation.

    This layer validates a signal before it reaches the
    global Risk Engine.

    It does NOT:
        - Calculate position size
        - Allocate capital
        - Place orders

    Those responsibilities belong to the platform Risk Engine.
    """

    def __init__(self, config: TB001Configuration) -> None:
        self.config = config

    def validate(
        self,
        context: MarketContext,
        signal: Signal | None,
    ) -> Signal | None:
        """
        Validate the generated signal.
        """

        if signal is None:
            return None

        if self._daily_loss_exceeded(context):
            return None

        if self._strategy_loss_exceeded(context):
            return None

        return signal

    def _daily_loss_exceeded(
        self,
        context: MarketContext,
    ) -> bool:
        """
        Daily loss protection.

        Placeholder implementation.
        """
        return False

    def _strategy_loss_exceeded(
        self,
        context: MarketContext,
    ) -> bool:
        """
        Strategy loss protection.

        Placeholder implementation.
        """
        return False

    def should_activate_kill_switch(
        self,
        context: MarketContext,
    ) -> bool:
        """
        Strategy emergency stop.

        Placeholder implementation.
        """
        return False