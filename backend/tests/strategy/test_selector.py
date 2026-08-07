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
from app.domains.strategy.credit_sellers import (
    BullPutSpreadStrategy,
    IronCondorStrategy,
)
from app.domains.strategy.selector import StrategySelector, default_selector
from app.domains.strategy.tb001 import TB001Strategy
from app.domains.strategy.tb002 import TB002Strategy


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


def test_selector_routes_low_vol_range_to_iron_fly():
    selector = default_selector()
    # Calm, low ADX + low IV -> RANGING + low vol -> TB001 Iron Fly.
    strategy = selector.select(_ctx(volatility_regime=VolatilityRegime.LOW, adx=10))
    assert isinstance(strategy, TB001Strategy)


def test_selector_routes_normal_vol_range_to_iron_condor():
    selector = default_selector()
    # Range with normal/high IV -> TB004 Iron Condor (defined risk, wider).
    strategy = selector.select(_ctx(volatility_regime=VolatilityRegime.NORMAL, adx=10))
    assert isinstance(strategy, IronCondorStrategy)


def test_selector_routes_uptrend_to_bull_put_spread():
    selector = default_selector()
    # Strong bullish trend -> TB005 Bull Put Spread (bullish credit).
    strategy = selector.select(
        _ctx(
            volatility_regime=VolatilityRegime.NORMAL,
            adx=30,
            trend=TrendDirection.BULLISH,
        )
    )
    assert isinstance(strategy, BullPutSpreadStrategy)


def test_selector_stands_aside_in_extreme_vol():
    # Extreme volatility -> tails too fat to sell -> stand aside (no strategy).
    selector = default_selector()
    strategy = selector.select(_ctx(volatility_regime=VolatilityRegime.EXTREME))
    assert strategy is None


def test_selector_routes_reversal_to_tb002():
    selector = default_selector()
    strategy = selector.select_for_regime(MarketRegime.REVERSAL)
    assert isinstance(strategy, TB002Strategy)


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
