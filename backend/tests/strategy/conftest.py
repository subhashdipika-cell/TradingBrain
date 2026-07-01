"""
Shared fixtures for strategy tests.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from app.domains.market.expiry import next_weekly_expiry, time_to_expiry_years
from app.domains.market.option_chain import build_synthetic_chain
from app.domains.market.symbol import NIFTY
from app.domains.shared.enums import (
    ExecutionMode,
    MarketRegime,
    TrendDirection,
    VolatilityRegime,
)
from app.domains.strategy.contracts import MarketContext, StrategyRegistry


@pytest.fixture(autouse=True)
def clean_registry():
    """Ensure each test starts and ends with an empty registry."""
    StrategyRegistry.clear()
    yield
    StrategyRegistry.clear()


@pytest.fixture
def entry_context() -> MarketContext:
    """A MarketContext that satisfies TB001's Phase-1 entry rules.

    Includes a synthetic ATM option chain in ``metadata`` because TB001 now
    selects the straddle strike and checks premium from the chain.
    """
    timestamp = datetime(2026, 6, 30, 9, 25)
    expiry = next_weekly_expiry(timestamp.date())
    chain = build_synthetic_chain(
        spec=NIFTY,
        spot=25_000.0,
        expiry=expiry,
        timestamp=timestamp,
        time_to_expiry=time_to_expiry_years(timestamp, expiry),
        implied_vol=0.13,
    )
    context = MarketContext(
        symbol="NIFTY",
        exchange="NSE",
        timeframe="5m",
        timestamp=timestamp,
        execution_mode=ExecutionMode.PAPER,
        market_regime=MarketRegime.RANGING,
        volatility_regime=VolatilityRegime.NORMAL,
        trend=TrendDirection.SIDEWAYS,
        is_market_open=True,
    )
    context.metadata["option_chain"] = chain
    context.metadata["strike_step"] = NIFTY.strike_step
    return context
