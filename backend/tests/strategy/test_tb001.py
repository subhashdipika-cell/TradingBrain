"""
Tests for TB001 - Dynamic Theta Harvesting strategy.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime

import pytest

from app.domains.shared.enums import (
    MarketRegime,
    OrderSide,
    PositionSide,
    SignalType,
    VolatilityRegime,
)
from app.domains.strategy.contracts import BaseStrategy, MarketContext, StrategyRegistry
from app.domains.strategy.tb001 import TB001Configuration, TB001Strategy
from app.domains.strategy.tb001.exceptions import StrategyConfigurationError


def test_tb001_is_a_base_strategy():
    assert issubclass(TB001Strategy, BaseStrategy)
    assert TB001Strategy.name == "TB001"


def test_tb001_registers():
    StrategyRegistry.register(TB001Strategy)
    assert StrategyRegistry.get("TB001") is TB001Strategy


def test_tb001_initialize_enables():
    strategy = TB001Strategy()
    assert strategy.enabled is False
    strategy.initialize()
    assert strategy.enabled is True


def test_tb001_generates_short_straddle_entry(entry_context: MarketContext):
    strategy = TB001Strategy()
    strategy.initialize()

    signal = strategy.generate_signal(entry_context)

    assert signal is not None
    assert signal.strategy == "TB001"
    assert signal.signal_type is SignalType.SELL
    assert signal.side is OrderSide.SELL
    assert signal.position_side is PositionSide.SHORT
    assert signal.reason == "Initial Short Straddle Entry"


def test_tb001_only_enters_once(entry_context: MarketContext):
    strategy = TB001Strategy()
    strategy.initialize()

    first = strategy.generate_signal(entry_context)
    second = strategy.generate_signal(entry_context)

    assert first is not None
    assert second is None  # position already open


def test_tb001_resets_position_state(entry_context: MarketContext):
    strategy = TB001Strategy()
    strategy.initialize()

    assert strategy.generate_signal(entry_context) is not None
    strategy.post_market(entry_context)  # triggers reset()
    assert strategy.generate_signal(entry_context) is not None


def test_tb001_no_entry_before_entry_time(entry_context: MarketContext):
    early = replace(entry_context, timestamp=datetime(2026, 6, 30, 9, 16))
    strategy = TB001Strategy()
    strategy.initialize()
    assert strategy.generate_signal(early) is None


def test_tb001_no_entry_when_market_closed(entry_context: MarketContext):
    closed = replace(entry_context, is_market_open=False)
    strategy = TB001Strategy()
    strategy.initialize()
    assert strategy.generate_signal(closed) is None


def test_tb001_no_entry_when_volatility_extreme(entry_context: MarketContext):
    extreme = replace(
        entry_context,
        volatility_regime=VolatilityRegime.EXTREME,
        market_regime=MarketRegime.VOLATILE,
    )
    strategy = TB001Strategy()
    strategy.initialize()
    assert strategy.generate_signal(extreme) is None


# ----------------------------------------------------------------------
# Configuration
# ----------------------------------------------------------------------
def test_configuration_defaults_are_valid():
    config = TB001Configuration()
    assert config.strategy_id == "TB001"
    assert config.entry_time_obj.hour == 9
    assert config.entry_time_obj.minute == 20


@pytest.mark.parametrize(
    "kwargs",
    [
        {"entry_time": "not-a-time"},
        {"max_daily_loss": 1.5},
        {"max_daily_loss": -0.1},
        {"min_premium": 0.0},
        {"shift_multiplier": -1.0},
        {"market_open": "15:30:00", "market_close": "09:15:00"},
    ],
)
def test_invalid_configuration_raises(kwargs):
    with pytest.raises(StrategyConfigurationError):
        TB001Configuration(**kwargs)
