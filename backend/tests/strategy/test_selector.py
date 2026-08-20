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
        implied_volatility=0.15,
        historical_volatility=0.10,
    )
    base.update(kwargs)
    return MarketContext(**base)


def test_selector_routes_rich_low_vol_range_to_iron_fly():
    selector = default_selector()
    # Calm, low ADX + low IV -> RANGING + low vol -> TB001 Iron Fly.
    strategy = selector.select(
        _ctx(
            volatility_regime=VolatilityRegime.LOW,
            implied_volatility=0.09,
            historical_volatility=0.08,
            adx=10,
        )
    )
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


def test_selector_keeps_extreme_rich_volatility_defined_risk():
    # Rich extreme volatility is eligible only through the hedged Iron Condor.
    selector = default_selector()
    strategy = selector.select(
        _ctx(
            volatility_regime=VolatilityRegime.EXTREME,
            implied_volatility=0.32,
            historical_volatility=0.20,
        )
    )
    assert isinstance(strategy, IronCondorStrategy)


def test_selector_rejects_cheap_volatility_with_diagnostics():
    selector = default_selector()
    ctx = _ctx(implied_volatility=0.12, historical_volatility=0.13, adx=10)

    assert selector.select(ctx) is None
    assert ctx.metadata["volatility_edge_gate"]["allowed"] is False
    assert "cheap volatility" in ctx.metadata["entry_rejection"]


def test_selector_rejects_event_risk_even_with_rich_volatility():
    selector = default_selector()
    ctx = _ctx(
        implied_volatility=0.25,
        historical_volatility=0.12,
        metadata={"event_risk": True},
    )

    assert selector.select(ctx) is None
    assert ctx.metadata["entry_rejection"] == "event risk active"


def test_selector_rejects_live_execution():
    selector = default_selector()
    ctx = _ctx(execution_mode=ExecutionMode.LIVE)

    assert selector.select(ctx) is None
    assert ctx.metadata["entry_rejection"] == "AUTO volatility-edge execution is PAPER-only"


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
