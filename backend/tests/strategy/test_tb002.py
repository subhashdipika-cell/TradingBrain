"""
Tests for TB002 - ICT Liquidity Sweep Inversion strategy.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime

import pytest

from app.domains.shared.enums import (
    ExecutionMode,
    MarketRegime,
    OrderSide,
    PositionSide,
    SignalType,
    TrendDirection,
    VolatilityRegime,
)
from app.domains.strategy.contracts import BaseStrategy, MarketContext, StrategyRegistry
from app.domains.strategy.tb002 import TB002Configuration, TB002Strategy
from app.domains.strategy.tb002.exceptions import StrategyConfigurationError


def _bearish_setup() -> dict:
    return {
        "direction": "BEARISH",
        "entry_price": 20_000.0,
        "stop_loss": 20_050.0,
        "first_target": 19_900.0,
        "external_target": 19_800.0,
        "runner_target": 19_750.0,
        "sweep": {
            "side": "BUY_SIDE",
            "timeframe": "daily",
            "reference_price": 20_100.0,
            "swept_price": 20_125.0,
        },
        "htf_inversion": {
            "direction": "BEARISH",
            "timeframe": "4h",
            "low": 19_980.0,
            "high": 20_080.0,
            "inverted": True,
            "candles_to_invert": 2,
        },
        "pullback_gap": {
            "direction": "BEARISH",
            "timeframe": "15m",
            "low": 19_995.0,
            "high": 20_020.0,
            "tapped": True,
            "inside_parent": True,
        },
        "trigger": {
            "direction": "BEARISH",
            "timeframe": "1m",
            "price": 20_000.0,
            "confirmed": True,
        },
    }


def _bullish_setup() -> dict:
    return {
        "direction": "BULLISH",
        "entry_price": 100.0,
        "stop_loss": 90.0,
        "first_target": 116.0,
        "external_target": 125.0,
        "sweep": {
            "side": "SELL_SIDE",
            "timeframe": "daily",
            "reference_price": 92.0,
            "swept_price": 89.5,
        },
        "htf_inversion": {
            "direction": "BULLISH",
            "timeframe": "4h",
            "low": 96.0,
            "high": 104.0,
            "inverted": True,
            "candles_to_invert": 1,
        },
        "pullback_gap": {
            "direction": "BULLISH",
            "timeframe": "15 minute",
            "low": 98.0,
            "high": 101.0,
            "tapped": True,
            "inside_parent": True,
        },
        "trigger": {
            "direction": "BULLISH",
            "timeframe": "5m",
            "price": 100.0,
            "confirmed": True,
        },
    }


def _context(setup: dict | None = None, **kwargs) -> MarketContext:
    base = dict(
        symbol="NQ",
        exchange="CME",
        timeframe="1m",
        timestamp=datetime(2026, 6, 30, 10, 0),
        execution_mode=ExecutionMode.PAPER,
        market_regime=MarketRegime.REVERSAL,
        volatility_regime=VolatilityRegime.HIGH,
        trend=TrendDirection.BEARISH,
        last_price=20_000.0,
        close_price=20_000.0,
        is_market_open=True,
    )
    base.update(kwargs)
    context = MarketContext(**base)
    if setup is not None:
        context.metadata["tb002_setup"] = setup
    return context


def test_tb002_is_a_base_strategy():
    assert issubclass(TB002Strategy, BaseStrategy)
    assert TB002Strategy.name == "TB002"


def test_tb002_registers():
    StrategyRegistry.register(TB002Strategy)
    assert StrategyRegistry.get("TB002") is TB002Strategy


def test_tb002_initialize_enables():
    strategy = TB002Strategy()
    assert strategy.enabled is False
    strategy.initialize()
    assert strategy.enabled is True


def test_tb002_generates_bearish_inversion_entry():
    strategy = TB002Strategy()
    strategy.initialize()

    signal = strategy.generate_signal(_context(_bearish_setup()))

    assert signal is not None
    assert signal.strategy == "TB002"
    assert signal.signal_type is SignalType.SELL
    assert signal.side is OrderSide.SELL
    assert signal.position_side is PositionSide.SHORT
    assert signal.entry_price == 20_000.0
    assert signal.stop_loss == 20_050.0
    assert signal.take_profit == 19_900.0
    assert signal.metadata["runner_target"] == 19_750.0
    assert signal.metadata["first_trim_fraction"] == 0.50


def test_tb002_generates_bullish_inversion_entry():
    strategy = TB002Strategy()
    strategy.initialize()

    signal = strategy.generate_signal(
        _context(
            _bullish_setup(),
            symbol="ES",
            last_price=100.0,
            close_price=100.0,
            trend=TrendDirection.BULLISH,
        )
    )

    assert signal is not None
    assert signal.signal_type is SignalType.BUY
    assert signal.side is OrderSide.BUY
    assert signal.position_side is PositionSide.LONG
    assert signal.take_profit == 116.0


def test_tb002_requires_complete_setup_metadata():
    strategy = TB002Strategy()
    strategy.initialize()

    assert strategy.generate_signal(_context()) is None


def test_tb002_rejects_unconfirmed_lower_timeframe_trigger():
    setup = _bearish_setup()
    setup["trigger"] = {**setup["trigger"], "confirmed": False}
    strategy = TB002Strategy()
    strategy.initialize()

    assert strategy.generate_signal(_context(setup)) is None


def test_tb002_rejects_bad_risk_reward():
    setup = _bearish_setup()
    setup["first_target"] = 19_975.0
    setup["external_target"] = 19_975.0
    strategy = TB002Strategy()
    strategy.initialize()

    assert strategy.generate_signal(_context(setup)) is None


def test_tb002_only_enters_once_until_reset():
    strategy = TB002Strategy()
    strategy.initialize()
    context = _context(_bearish_setup())

    first = strategy.generate_signal(context)
    second = strategy.generate_signal(context)
    strategy.reset()
    third = strategy.generate_signal(context)

    assert first is not None
    assert second is None
    assert third is not None


def test_tb002_no_entry_when_market_closed():
    strategy = TB002Strategy()
    strategy.initialize()

    assert (
        strategy.generate_signal(
            replace(_context(_bearish_setup()), is_market_open=False)
        )
        is None
    )


def test_tb002_manage_position_can_emit_exit_signal():
    strategy = TB002Strategy()
    strategy.initialize()
    context = _context(_bearish_setup())
    assert strategy.generate_signal(context) is not None

    context.metadata["tb002_position"] = {
        "structure_invalidated": True,
        "reason": "15m high reclaimed",
    }
    exit_signal = strategy.manage_position(context)

    assert exit_signal is not None
    assert exit_signal.signal_type is SignalType.EXIT
    assert exit_signal.side is OrderSide.BUY
    assert exit_signal.position_side is PositionSide.FLAT


def test_tb002_configuration_defaults_are_valid():
    config = TB002Configuration()
    assert config.strategy_id == "TB002"
    assert config.min_risk_reward == 1.5


@pytest.mark.parametrize(
    "kwargs",
    [
        {"entry_start": "not-a-time"},
        {"max_daily_loss": 1.2},
        {"min_risk_reward": 0.0},
        {"max_setup_age_minutes": 0},
        {"trigger_timeframes": ()},
        {"market_open": "15:30:00", "market_close": "09:15:00"},
    ],
)
def test_tb002_invalid_configuration_raises(kwargs):
    with pytest.raises(StrategyConfigurationError):
        TB002Configuration(**kwargs)
