"""
Tests for TB007 - Convexity Buy (low-IV squeeze-break long option).
"""

from __future__ import annotations

from datetime import datetime

import pytest

from app.domains.shared.enums import (
    ExecutionMode,
    MarketRegime,
    OrderSide,
    PositionSide,
    SignalType,
    VolatilityRegime,
)
from app.domains.strategy.contracts import BaseStrategy, MarketContext, StrategyRegistry
from app.domains.strategy.tb007 import TB007Configuration, TB007Strategy
from app.domains.strategy.tb007.configuration import StrategyConfigurationError


def _ctx(
    *,
    iv: float = 0.10,
    squeeze: bool = True,
    price: float = 25_120.0,
    bb_upper: float = 25_100.0,
    bb_lower: float = 24_900.0,
    bb_mid: float = 25_000.0,
    hour: int = 11,
    is_expiry: bool = False,
) -> MarketContext:
    """Build a context that (by default) satisfies every TB007 gate with an
    upside squeeze-break."""
    ctx = MarketContext(
        symbol="NIFTY",
        exchange="NSE",
        timeframe="5m",
        timestamp=datetime(2026, 6, 30, hour, 20),
        execution_mode=ExecutionMode.BACKTEST,
        market_regime=MarketRegime.RANGING,
        volatility_regime=VolatilityRegime.LOW,
        implied_volatility=iv,
        last_price=price,
        close_price=price,
        is_market_open=True,
        is_expiry=is_expiry,
    )
    ctx.indicators.update(
        {
            "squeeze": squeeze,
            "bb_upper": bb_upper,
            "bb_lower": bb_lower,
            "bb_mid": bb_mid,
            "bb_bandwidth": 0.008,
        }
    )
    return ctx


@pytest.fixture(autouse=True)
def clean_registry():
    StrategyRegistry.clear()
    yield
    StrategyRegistry.clear()


def test_tb007_is_a_base_strategy():
    assert issubclass(TB007Strategy, BaseStrategy)
    assert TB007Strategy.name == "TB007"


def test_tb007_registers():
    StrategyRegistry.register(TB007Strategy)
    assert StrategyRegistry.get("TB007") is TB007Strategy


def test_tb007_initialize_enables():
    strat = TB007Strategy()
    assert strat.enabled is False
    strat.initialize()
    assert strat.enabled is True


def test_tb007_buys_call_on_upside_squeeze_break():
    strat = TB007Strategy()
    strat.initialize()

    signal = strat.generate_signal(_ctx(price=25_120.0))  # breaks above upper band

    assert signal is not None
    assert signal.strategy == "TB007"
    assert signal.signal_type is SignalType.BUY
    assert signal.side is OrderSide.BUY
    assert signal.position_side is PositionSide.LONG  # -> long CALL (defined risk)
    # No legs -> engine routes to the directional (debit) path.
    assert "legs" not in signal.metadata
    # Asymmetric, defined risk: stop at the band mid, target target_r x risk away.
    assert signal.stop_loss == pytest.approx(25_000.0)
    risk = signal.entry_price - signal.stop_loss
    assert signal.take_profit == pytest.approx(
        signal.entry_price + strat.configuration.target_r * risk
    )
    assert 0.0 < signal.requested_risk <= 0.02


def test_tb007_buys_put_on_downside_squeeze_break():
    strat = TB007Strategy()
    strat.initialize()

    signal = strat.generate_signal(_ctx(price=24_880.0))  # breaks below lower band

    assert signal is not None
    assert signal.position_side is PositionSide.SHORT  # -> long PUT
    assert signal.stop_loss == pytest.approx(25_000.0)
    assert signal.take_profit < signal.entry_price


def test_tb007_rejects_expensive_iv():
    strat = TB007Strategy()
    strat.initialize()
    # IV above the cheap ceiling -> no trade (convexity not on sale).
    assert strat.generate_signal(_ctx(iv=0.30)) is None


def test_tb007_rejects_without_squeeze():
    strat = TB007Strategy()
    strat.initialize()
    # Breaking out but never coiled -> not a convex setup, just chasing.
    assert strat.generate_signal(_ctx(squeeze=False)) is None


def test_tb007_rejects_inside_the_bands():
    strat = TB007Strategy()
    strat.initialize()
    # Coiled + cheap but no break yet -> wait, don't pay decay on a guess.
    assert strat.generate_signal(_ctx(price=25_000.0)) is None


def test_tb007_blocks_expiry_day_zero_dte():
    strat = TB007Strategy()
    strat.initialize()
    assert strat.generate_signal(_ctx(is_expiry=True)) is None


def test_tb007_respects_entry_window():
    strat = TB007Strategy()
    strat.initialize()
    # 09:20 is inside the 09:15-10:15 open the platform blocks -> no entry.
    assert strat.generate_signal(_ctx(hour=9)) is None


def test_tb007_squeeze_grace_allows_break_a_few_bars_later():
    strat = TB007Strategy()
    strat.initialize()
    # Bar 1: coiled, inside bands -> no signal but grace window is armed.
    assert strat.generate_signal(_ctx(price=25_000.0, squeeze=True)) is None
    # Bar 2: squeeze flag gone, but the break happens within grace -> fires.
    signal = strat.generate_signal(_ctx(price=25_120.0, squeeze=False))
    assert signal is not None


def test_tb007_config_validation_rejects_bad_iv_ceiling():
    with pytest.raises(StrategyConfigurationError):
        TB007Configuration(max_entry_iv=1.5)


# ── Neutral straddle mode ─────────────────────────────────────────────────────
def _straddle_ctx(**kw) -> MarketContext:
    """A cheap + coiled context with an ATM option chain for straddle mode."""
    from app.domains.market.expiry import next_weekly_expiry, time_to_expiry_years
    from app.domains.market.option_chain import build_synthetic_chain
    from app.domains.market.symbol import NIFTY

    ctx = _ctx(price=25_000.0, **kw)  # inside the bands: no directional break
    ts = ctx.timestamp
    expiry = next_weekly_expiry(ts.date())
    ctx.metadata["option_chain"] = build_synthetic_chain(
        spec=NIFTY,
        spot=25_000.0,
        expiry=expiry,
        timestamp=ts,
        time_to_expiry=time_to_expiry_years(ts, expiry),
        implied_vol=0.10,
    )
    return ctx


def test_tb007_neutral_mode_buys_straddle_without_a_directional_break():
    strat = TB007Strategy()
    strat.configuration.neutral_straddle = True
    strat.initialize()

    # Price sitting ON the mid (no break) still triggers a straddle in neutral
    # mode - the bet is on magnitude, not direction.
    signal = strat.generate_signal(_straddle_ctx())

    assert signal is not None
    assert signal.metadata["structure"] == "LONG_STRADDLE"
    legs = signal.metadata["straddle_legs"]
    assert len(legs) == 2
    assert {leg["right"] for leg in legs} == {"CALL", "PUT"}
    assert all(leg["side"] == "BUY" for leg in legs)  # both legs long = long vol
    assert "legs" not in signal.metadata  # not the credit path
    assert 0.0 < signal.metadata["target_profit_pct"] <= 1.0


def test_tb007_neutral_mode_still_requires_cheap_and_coiled():
    strat = TB007Strategy()
    strat.configuration.neutral_straddle = True
    strat.initialize()
    # Expensive IV -> no straddle even though coiled.
    assert strat.generate_signal(_straddle_ctx(iv=0.30)) is None


def test_tb007_straddle_passes_overnight_hold_intent_to_engine():
    strat = TB007Strategy()
    strat.configuration.neutral_straddle = True
    strat.configuration.hold_overnight = True
    strat.configuration.max_hold_sessions = 3
    strat.initialize()

    signal = strat.generate_signal(_straddle_ctx())
    assert signal is not None
    assert signal.metadata["hold_overnight"] is True
    assert signal.metadata["max_hold_sessions"] == 3


def test_tb007_straddle_defaults_to_intraday():
    strat = TB007Strategy()
    strat.configuration.neutral_straddle = True
    strat.initialize()
    signal = strat.generate_signal(_straddle_ctx())
    assert signal is not None
    assert signal.metadata["hold_overnight"] is False
