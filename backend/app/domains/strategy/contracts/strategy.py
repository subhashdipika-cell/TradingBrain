"""
TradingBrain
Abstract Base Strategy Contract

Every TradingBrain strategy (TB001..TB999) inherits from ``BaseStrategy``.

The base class defines the *shape* of a strategy - its identity, its runtime
state and the lifecycle hooks the platform invokes during a trading session.
It deliberately contains no trading logic: concrete strategies supply that by
implementing the abstract lifecycle methods.

Lifecycle
---------
1. ``initialize()``       - one-time setup (called once before trading).
2. ``pre_market()``       - per-session preparation, before the open.
3. ``generate_signal()``  - produce an entry signal for the current bar.
4. ``manage_position()``  - manage an already-open position.
5. ``manage_risk()``      - apply strategy-level risk hooks.
6. ``post_market()``      - end-of-day processing, after the close.
7. ``reset()``            - reset internal state for the next session.

Author: TradingBrain
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.domains.strategy.contracts.context import MarketContext
from app.domains.strategy.contracts.signal import Signal
from app.domains.strategy.contracts.state import State


class BaseStrategy(ABC):
    """
    Abstract base class for all TradingBrain strategies.

    Subclasses must override the identity class attributes
    (``name``, ``version``, ``description``) and implement every
    abstract lifecycle method.
    """

    # ------------------------------------------------------------------
    # Identity (overridden by concrete strategies)
    # ------------------------------------------------------------------
    name: str = "BASE"
    version: str = "0.0.0"
    description: str = "Abstract base strategy"

    def __init__(self) -> None:
        # Whether the strategy is allowed to act. Concrete strategies
        # typically flip this to True inside ``initialize()``.
        self.enabled: bool = False

        # Runtime state maintained across the lifecycle.
        self.state: State = State()

    # ------------------------------------------------------------------
    # Lifecycle hooks (must be implemented by concrete strategies)
    # ------------------------------------------------------------------
    @abstractmethod
    def initialize(self) -> None:
        """
        Perform one-time setup before trading begins.
        """
        raise NotImplementedError

    @abstractmethod
    def pre_market(self, context: MarketContext) -> None:
        """
        Prepare the strategy before the market opens.
        """
        raise NotImplementedError

    @abstractmethod
    def generate_signal(self, context: MarketContext) -> Signal | None:
        """
        Generate a trading signal for the current market context.

        Returns ``None`` when no action should be taken.
        """
        raise NotImplementedError

    @abstractmethod
    def manage_position(self, context: MarketContext) -> Signal | None:
        """
        Manage an open position.

        May return an exit/adjustment signal, or ``None`` to hold.
        """
        raise NotImplementedError

    @abstractmethod
    def manage_risk(self, context: MarketContext) -> None:
        """
        Apply strategy-specific risk rules.
        """
        raise NotImplementedError

    @abstractmethod
    def post_market(self, context: MarketContext) -> None:
        """
        Perform end-of-day processing after the market closes.
        """
        raise NotImplementedError

    @abstractmethod
    def reset(self) -> None:
        """
        Reset internal strategy state for the next trading session.
        """
        raise NotImplementedError

    # ------------------------------------------------------------------
    # Convenience helpers (available to every strategy)
    # ------------------------------------------------------------------
    def enable(self) -> None:
        """Allow the strategy to act."""
        self.enabled = True

    def disable(self) -> None:
        """Prevent the strategy from acting."""
        self.enabled = False

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return (
            f"<{self.__class__.__name__} "
            f"name={self.name} "
            f"version={self.version} "
            f"enabled={self.enabled}>"
        )
