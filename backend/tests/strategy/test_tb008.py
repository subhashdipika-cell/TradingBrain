"""Tests for TB008 - Adaptive Calendar Spread Engine."""

from __future__ import annotations

from datetime import date, datetime

import pytest

from app.domains.market.expiry import time_to_expiry_years
from app.domains.market.option_chain import build_synthetic_chain
from app.domains.market.symbol import NIFTY
from app.domains.shared.enums import ExecutionMode
from app.domains.strategy.contracts.context import MarketContext
from app.domains.strategy.contracts.registry import StrategyRegistry
from app.domains.strategy.selector import register_all_strategies
from app.domains.strategy.tb008 import TB008Configuration, TB008Strategy
from app.domains.strategy.tb008.models import VixLevel
from app.domains.strategy.tb008.regime import VixRegimeClassifier

NOW = datetime(2026, 7, 3, 9, 30)
NEAR = date(2026, 7, 9)
FAR = date(2026, 7, 16)


def _chain(expiry, spot=24000.0, iv=0.13):
    return build_synthetic_chain(
        spec=NIFTY,
        spot=spot,
        expiry=expiry,
        timestamp=NOW,
        time_to_expiry=time_to_expiry_years(NOW, expiry),
        implied_vol=iv,
        strikes_each_side=40,
    )


def _context(*, with_far=True, vix=12.9):
    ctx = MarketContext(
        symbol="NIFTY",
        exchange="NSE",
        timeframe="1d",
        timestamp=NOW,
        execution_mode=ExecutionMode.BACKTEST,
        last_price=24000.0,
        implied_volatility=0.13,
        vix=vix,
        is_market_open=True,
    )
    ctx.metadata["option_chain"] = _chain(NEAR)
    if with_far:
        ctx.metadata["option_chain_far"] = _chain(FAR)
    ctx.metadata["lot_size"] = 75
    return ctx


# ----------------------------------------------------------------------
# Regime gating
# ----------------------------------------------------------------------
def test_vix_regime_classifier():
    clf = VixRegimeClassifier(TB008Configuration())
    assert clf.assess(12.0).level is VixLevel.LOW
    assert clf.assess(12.0).favorable is True
    assert clf.assess(18.0).level is VixLevel.MEDIUM
    assert clf.assess(25.0).level is VixLevel.HIGH
    assert clf.assess(25.0).favorable is False
    assert clf.assess(10.0).expansion_risk is True
    # A sharp jump = expanding vol -> not favourable even if still low.
    assert clf.assess(13.5, prior_vix=11.0).favorable is False


def test_tb008_stands_aside_without_far_chain():
    strategy = TB008Strategy()
    strategy.initialize()
    assert strategy.generate_signal(_context(with_far=False)) is None


def test_tb008_stands_aside_in_high_vix():
    strategy = TB008Strategy()
    strategy.initialize()
    assert strategy.generate_signal(_context(vix=26.0)) is None


# ----------------------------------------------------------------------
# Structure + payoff
# ----------------------------------------------------------------------
def test_tb008_builds_double_calendar_in_low_vix():
    strategy = TB008Strategy()
    strategy.initialize()
    signal = strategy.generate_signal(_context())

    assert signal is not None
    meta = signal.metadata
    assert meta["structure"] == "DOUBLE_CALENDAR"
    assert meta["requires_multi_expiry"] is True

    legs = meta["calendar_legs"]
    sells = [leg for leg in legs if leg["side"] == "SELL"]
    buys = [leg for leg in legs if leg["side"] == "BUY"]
    assert len(sells) == 2  # near call + put (the short strangle)
    assert all(leg["expiry_bucket"] == "near" for leg in sells)
    assert len(buys) == 4  # ratio hedges on the far expiry (2 per side)
    assert all(leg["expiry_bucket"] == "far" for leg in buys)

    # Payoff: bounded loss, positive peak, flat MTM (the "safe feeling").
    assert meta["max_profit"] > 0
    assert meta["max_loss"] > -meta["margin"]  # loss well inside margin
    assert meta["margin"] > 0
    assert 0.0 <= meta["mtm_smoothness"] <= 1.0
    assert meta["mtm_smoothness"] > 0.4  # notably flatter than a raw strangle


def test_tb008_enters_once_then_resets():
    strategy = TB008Strategy()
    strategy.initialize()
    ctx = _context()
    assert strategy.generate_signal(ctx) is not None
    assert strategy.generate_signal(ctx) is None  # position already open
    strategy.post_market(ctx)  # resets
    assert strategy.generate_signal(_context()) is not None


def test_tb008_registered_in_registry():
    StrategyRegistry.clear()
    register_all_strategies()
    assert StrategyRegistry.exists("TB008")
    assert StrategyRegistry.get("TB008") is TB008Strategy


def test_tb008_config_validation():
    from app.domains.strategy.tb008.exceptions import StrategyConfigurationError

    with pytest.raises(StrategyConfigurationError):
        TB008Configuration(target_sell_delta=1.5)
    with pytest.raises(StrategyConfigurationError):
        TB008Configuration(sell_lots=0)
