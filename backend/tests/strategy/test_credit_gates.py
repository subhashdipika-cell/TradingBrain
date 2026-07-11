"""Tests for the credit-seller tuning gates (trend veto + min-credit hurdle).

Added after the Jul-2026 real-data audit: TB005 was PF 0.37 selling bull puts
into declines, and TB004 banked less decay than it paid in transaction costs.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime

from app.domains.market.expiry import next_weekly_expiry, time_to_expiry_years
from app.domains.market.option_chain import build_synthetic_chain
from app.domains.market.symbol import NIFTY
from app.domains.shared.enums import ExecutionMode, TrendDirection
from app.domains.strategy.contracts import MarketContext
from app.domains.strategy.credit_sellers import (
    BearCallSpreadStrategy,
    BullPutSpreadStrategy,
    IronCondorStrategy,
)


def _context(trend: TrendDirection = TrendDirection.SIDEWAYS) -> MarketContext:
    when = datetime(2026, 6, 30, 11, 0)
    expiry = next_weekly_expiry(when.date())
    chain = build_synthetic_chain(
        spec=NIFTY,
        spot=25_000.0,
        expiry=expiry,
        timestamp=when,
        time_to_expiry=time_to_expiry_years(when, expiry),
        implied_vol=0.13,
    )
    ctx = MarketContext(
        symbol="NIFTY",
        exchange="NSE",
        timeframe="1m",
        timestamp=when,
        execution_mode=ExecutionMode.BACKTEST,
        trend=trend,
        last_price=25_000.0,
        close_price=25_000.0,
        is_market_open=True,
        minutes_from_open=105,
        minutes_to_close=270,
    )
    ctx.metadata["option_chain"] = chain
    ctx.metadata["strike_step"] = NIFTY.strike_step
    return ctx


# ── trend veto ─────────────────────────────────────────────────────────────────
def test_tb005_refuses_bearish_tape():
    strat = BullPutSpreadStrategy()
    assert strat.generate_signal(_context(TrendDirection.BEARISH)) is None


def test_tb005_trades_non_bearish_tape():
    strat = BullPutSpreadStrategy()
    strat.configuration = replace(strat.configuration, min_entry_credit=0.0)
    assert strat.generate_signal(_context(TrendDirection.SIDEWAYS)) is not None


def test_tb006_refuses_bullish_tape():
    strat = BearCallSpreadStrategy()
    assert strat.generate_signal(_context(TrendDirection.BULLISH)) is None


def test_tb006_trades_non_bullish_tape():
    strat = BearCallSpreadStrategy()
    strat.configuration = replace(strat.configuration, min_entry_credit=0.0)
    assert strat.generate_signal(_context(TrendDirection.BEARISH)) is not None


def test_trend_gate_can_be_disabled():
    strat = BullPutSpreadStrategy()
    strat.configuration = replace(
        strat.configuration, trend_gate=False, min_entry_credit=0.0
    )
    assert strat.generate_signal(_context(TrendDirection.BEARISH)) is not None


# ── min-credit cost hurdle ─────────────────────────────────────────────────────
def test_min_entry_credit_blocks_small_tickets():
    strat = IronCondorStrategy()
    strat.configuration = replace(strat.configuration, min_entry_credit=10_000.0)
    assert strat.generate_signal(_context()) is None


def test_min_entry_credit_zero_allows_entry():
    strat = IronCondorStrategy()
    strat.configuration = replace(strat.configuration, min_entry_credit=0.0)
    assert strat.generate_signal(_context()) is not None


def test_tuned_defaults_from_audit():
    # Values chosen in the 2026-07-11 real-data sweep - guard against drift.
    assert IronCondorStrategy().configuration.min_entry_credit == 8.0
    assert BullPutSpreadStrategy().configuration.min_entry_credit == 8.0
    assert BearCallSpreadStrategy().configuration.min_entry_credit == 4.0
    assert BullPutSpreadStrategy().configuration.trend_gate is True
    assert BearCallSpreadStrategy().configuration.trend_gate is True
