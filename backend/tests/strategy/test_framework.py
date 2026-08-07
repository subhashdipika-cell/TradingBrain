"""
Tests for the strategy framework contracts (TB-003).
"""

from __future__ import annotations

import pytest

from app.domains.shared.enums import StrategyState
from app.domains.strategy.contracts import (
    BaseStrategy,
    MarketContext,
    Signal,
    State,
    StrategyRegistry,
)


def test_base_strategy_is_abstract():
    """BaseStrategy cannot be instantiated directly."""
    with pytest.raises(TypeError):
        BaseStrategy()  # type: ignore[abstract]


def test_base_strategy_requires_all_lifecycle_methods():
    """A subclass missing a lifecycle hook stays abstract."""

    class Incomplete(BaseStrategy):
        def initialize(self) -> None:  # pragma: no cover - never called
            ...

    with pytest.raises(TypeError):
        Incomplete()  # type: ignore[abstract]


def _make_concrete() -> type[BaseStrategy]:
    class Dummy(BaseStrategy):
        name = "DUMMY"
        version = "9.9.9"
        description = "Test strategy"

        def initialize(self) -> None:
            self.enable()

        def pre_market(self, context: MarketContext) -> None: ...

        def generate_signal(self, context: MarketContext) -> Signal | None:
            return None

        def manage_position(self, context: MarketContext) -> Signal | None:
            return None

        def manage_risk(self, context: MarketContext) -> None: ...

        def post_market(self, context: MarketContext) -> None: ...

        def reset(self) -> None: ...

    return Dummy


def test_concrete_strategy_defaults():
    strategy = _make_concrete()()
    assert strategy.enabled is False
    assert isinstance(strategy.state, State)
    assert strategy.state.state is StrategyState.INITIALIZED

    strategy.initialize()
    assert strategy.enabled is True

    strategy.disable()
    assert strategy.enabled is False


def test_registry_register_and_get():
    cls = _make_concrete()
    StrategyRegistry.register(cls)

    assert StrategyRegistry.exists("DUMMY")
    assert StrategyRegistry.get("DUMMY") is cls
    assert StrategyRegistry.list() == ["DUMMY"]


def test_registry_get_unknown_raises():
    with pytest.raises(KeyError):
        StrategyRegistry.get("NOPE")


def test_registry_unregister_and_clear():
    cls = _make_concrete()
    StrategyRegistry.register(cls)

    StrategyRegistry.unregister("DUMMY")
    assert not StrategyRegistry.exists("DUMMY")

    StrategyRegistry.register(cls)
    StrategyRegistry.clear()
    assert StrategyRegistry.list() == []
