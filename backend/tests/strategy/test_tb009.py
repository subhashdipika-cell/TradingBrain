"""Tests for TB009 Range Breakout Credit."""

from __future__ import annotations

from datetime import datetime, timedelta

from app.domains.market.candle import Candle
from app.domains.market.expiry import next_weekly_expiry, time_to_expiry_years
from app.domains.market.option_chain import build_synthetic_chain
from app.domains.market.symbol import NIFTY
from app.domains.shared.enums import ExecutionMode, OptionRight
from app.domains.strategy.contracts import MarketContext
from app.domains.strategy.range_breakout import RangeBreakoutCreditStrategy


def _candles(day: datetime, low: float, high: float, bars: int = 24) -> list[Candle]:
    """5m bars 09:15..11:10 oscillating inside [low, high]."""
    out = []
    start = day.replace(hour=9, minute=15)
    for i in range(bars):
        ts = start + timedelta(minutes=5 * i)
        mid = (low + high) / 2
        px = low if i % 2 == 0 else high
        out.append(Candle(timestamp=ts, open=mid, high=px if px == high else mid,
                          low=px if px == low else mid, close=mid))
    return out


def _context(spot: float, when: datetime, candles: list[Candle]) -> MarketContext:
    expiry = next_weekly_expiry(when.date())
    chain = build_synthetic_chain(
        spec=NIFTY,
        spot=spot,
        expiry=expiry,
        timestamp=when,
        time_to_expiry=time_to_expiry_years(when, expiry),
        implied_vol=0.13,
    )
    ctx = MarketContext(
        symbol="NIFTY",
        exchange="NSE",
        timeframe="5m",
        timestamp=when,
        execution_mode=ExecutionMode.PAPER,
        last_price=spot,
        is_market_open=True,
        minutes_to_close=240,
    )
    ctx.metadata["option_chain"] = chain
    ctx.metadata["session_candles"] = candles
    return ctx


DAY = datetime(2026, 6, 30)


def test_breakout_above_range_sells_itm_put_spread():
    candles = _candles(DAY, low=24950.0, high=25050.0)
    ctx = _context(spot=25100.0, when=DAY.replace(hour=11, minute=25), candles=candles)
    sig = RangeBreakoutCreditStrategy().generate_signal(ctx)
    assert sig is not None
    meta = sig.metadata
    assert meta["structure"] == "BULL_PUT_SPREAD"
    legs = {leg["side"]: leg for leg in meta["legs"]}
    assert legs["SELL"]["right"] == "PUT"
    assert legs["SELL"]["strike"] > 25100.0      # ITM put: strike above spot
    assert legs["BUY"]["strike"] < legs["SELL"]["strike"]  # hedge below
    assert meta["entry_credit"] > 0
    assert meta["wing_width"] == legs["SELL"]["strike"] - legs["BUY"]["strike"]


def test_breakdown_below_range_sells_itm_call_spread():
    candles = _candles(DAY, low=24950.0, high=25050.0)
    ctx = _context(spot=24900.0, when=DAY.replace(hour=11, minute=25), candles=candles)
    sig = RangeBreakoutCreditStrategy().generate_signal(ctx)
    assert sig is not None
    meta = sig.metadata
    assert meta["structure"] == "BEAR_CALL_SPREAD"
    legs = {leg["side"]: leg for leg in meta["legs"]}
    assert legs["SELL"]["right"] == "CALL"
    assert legs["SELL"]["strike"] < 24900.0      # ITM call: strike below spot
    assert legs["BUY"]["strike"] > legs["SELL"]["strike"]  # hedge above


def test_inside_range_no_signal():
    candles = _candles(DAY, low=24950.0, high=25050.0)
    ctx = _context(spot=25000.0, when=DAY.replace(hour=11, minute=25), candles=candles)
    assert RangeBreakoutCreditStrategy().generate_signal(ctx) is None


def test_before_range_complete_no_signal():
    candles = _candles(DAY, low=24950.0, high=25050.0)
    ctx = _context(spot=25100.0, when=DAY.replace(hour=10, minute=30), candles=candles)
    assert RangeBreakoutCreditStrategy().generate_signal(ctx) is None


def test_thin_range_coverage_stands_aside():
    candles = _candles(DAY, low=24950.0, high=25050.0, bars=10)  # < min_range_bars
    ctx = _context(spot=25100.0, when=DAY.replace(hour=11, minute=25), candles=candles)
    assert RangeBreakoutCreditStrategy().generate_signal(ctx) is None


def test_one_entry_per_session():
    candles = _candles(DAY, low=24950.0, high=25050.0)
    strat = RangeBreakoutCreditStrategy()
    ctx = _context(spot=25100.0, when=DAY.replace(hour=11, minute=25), candles=candles)
    assert strat.generate_signal(ctx) is not None
    ctx2 = _context(spot=25200.0, when=DAY.replace(hour=12, minute=0), candles=candles)
    assert strat.generate_signal(ctx2) is None
