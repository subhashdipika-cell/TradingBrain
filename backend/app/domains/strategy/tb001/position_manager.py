"""
TradingBrain

TB001 - Position Manager
"""

from __future__ import annotations

from app.domains.strategy.contracts.context import MarketContext
from app.domains.strategy.contracts.signal import Signal
from app.domains.strategy.tb001.configuration import TB001Configuration


class PositionManager:
    """
    Manages strategy positions.

    Responsibilities
    ----------------
    - Open position decisions
    - Position adjustment
    - Strike rolling
    - Position closure

    Does NOT
    --------
    - Generate entry signals
    - Calculate risk
    - Place broker orders
    """

    def __init__(self, config: TB001Configuration) -> None:
        self._config = config

    def manage(
        self,
        context: MarketContext,
        signal: Signal | None,
    ) -> Signal | None:
        """
        Manage the current strategy position.

        Future versions will:
            - Roll strikes
            - Scale positions
            - Trail profits
            - Handle partial exits
        """
        return signal

    def should_roll_position(
        self,
        context: MarketContext,
    ) -> bool:
        """
        Decide whether the position should be rolled.
        """
        return False

    def should_scale_position(
        self,
        context: MarketContext,
    ) -> bool:
        """
        Decide whether additional quantity should be added.
        """
        return False

    def should_reduce_position(
        self,
        context: MarketContext,
    ) -> bool:
        """
        Decide whether exposure should be reduced.
        """
        return False

    def should_close_position(
        self,
        context: MarketContext,
    ) -> bool:
        """
        Decide whether the current position should be closed.
        """
        return False