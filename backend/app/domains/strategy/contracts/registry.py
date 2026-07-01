"""
TradingBrain
Strategy Registry
"""

from __future__ import annotations

from typing import Type

from app.domains.strategy.contracts.strategy import BaseStrategy


class StrategyRegistry:
    """
    Registry for all TradingBrain strategies.
    """

    _strategies: dict[str, Type[BaseStrategy]] = {}

    @classmethod
    def register(
        cls,
        strategy_class: Type[BaseStrategy],
    ) -> None:
        """
        Register a strategy class.
        """
        cls._strategies[strategy_class.name] = strategy_class

    @classmethod
    def unregister(
        cls,
        strategy_name: str,
    ) -> None:
        """
        Remove a strategy from the registry.
        """
        cls._strategies.pop(strategy_name, None)

    @classmethod
    def get(
        cls,
        strategy_name: str,
    ) -> Type[BaseStrategy]:
        """
        Get a registered strategy.
        """
        if strategy_name not in cls._strategies:
            raise KeyError(f"Strategy '{strategy_name}' is not registered.")

        return cls._strategies[strategy_name]

    @classmethod
    def exists(
        cls,
        strategy_name: str,
    ) -> bool:
        """
        Check whether a strategy is registered.
        """
        return strategy_name in cls._strategies

    @classmethod
    def list(cls) -> list[str]:
        """
        Return registered strategy names.
        """
        return sorted(cls._strategies.keys())

    @classmethod
    def clear(cls) -> None:
        """
        Remove all registered strategies.
        """
        cls._strategies.clear()