"""
TradingBrain
Strategy Framework - Public Contracts

This package defines the shared contracts every strategy (TB001..TB999)
builds upon:

- :class:`BaseStrategy`     - abstract strategy lifecycle.
- :class:`MarketContext`    - standardized market information.
- :class:`Signal`           - standardized strategy output.
- :class:`State`            - runtime strategy state.
- :class:`StrategyRegistry` - registry of available strategies.
"""

from app.domains.strategy.contracts.context import MarketContext
from app.domains.strategy.contracts.registry import StrategyRegistry
from app.domains.strategy.contracts.signal import Signal
from app.domains.strategy.contracts.state import State
from app.domains.strategy.contracts.strategy import BaseStrategy

__all__ = [
    "BaseStrategy",
    "MarketContext",
    "Signal",
    "State",
    "StrategyRegistry",
]
