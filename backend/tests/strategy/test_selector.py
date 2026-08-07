"""Tests for the regime-based strategy selector."""

from __future__ import annotations

from datetime import datetime

import pytest

from app.domains.shared.enums import (
    ExecutionMode,
    MarketRegime,
    TrendDirection,
    VolatilityRegime,
)
from app.domains.strategy.contracts import MarketContext
from app.domains.strategy.contracts.registry import StrategyRegistry
from app.domains.strategy.selector import StrategySelector, default_selector
from app.domains.strategy.tb001 import TB001Strategy


def _ctx(**kwargs) -> MarketContext:
    base = dict(
        symbol="NIFTY",
        exchange="NSE",
        timeframe="5m",
        timestamp=datetime(2026, 6, 30, 9, 25),
        execution_mode=ExecutionMode.BACKTEST,
    )
    base.update(kwargs)
    return MarketContext(**base)


def test_selector_routes_ranging_to_tb001():
    selector = default_selector()
    # Calm, low ADX -> RANGING -> TB001 selected.
    strategy = selector.select(_ctx(volatility_regime=VolatilityRegime.NORMAL, adx=10))
    assert isinstance(strategy, TB001Strategy)


def test_selector_sits_out_trending():
    selector = default_selector()
    # Strong trend -> TRENDING -> no strategy mapped -> None.
    strategy = selector.select(
        _ctx(
            volatility_regime=VolatilityRegime.NORMAL,
            adx=30,
            trend=TrendDirection.BULLISH,
        )
    )
    assert strategy is None


def test_selector_sits_out_high_volatility():
    selector = default_selector()
    strategy = selector.select(_ctx(volatility_regime=VolatilityRegime.EXTREME))
    assert strategy is None  # VOLATILE regime not mapped


def test_selector_caches_instances():
    selector = default_selector()
    a = selector.select(_ctx(volatility_regime=VolatilityRegime.NORMAL, adx=10))
    b = selector.select(_ctx(volatility_regime=VolatilityRegime.NORMAL, adx=10))
    assert a is b  # same instance reused so lifecycle state persists


def test_mapping_requires_registered_strategy():
    StrategyRegistry.clear()
    selector = StrategySelector()
    with pytest.raises(KeyError):
        selector.map_regime(MarketRegime.RANGING, "TB999")


def test_select_sets_context_regime():
    selector = default_selector()
    ctx = _ctx(volatility_regime=VolatilityRegime.NORMAL, adx=10)
    selector.select(ctx)
    assert ctx.market_regime is MarketRegime.RANGING
