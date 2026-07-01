"""Tests for the TB002 ICT primitives and setup detector."""

from __future__ import annotations

from datetime import datetime, timedelta

from app.domains.market.candle import Candle
from app.domains.shared.enums import (
    ExecutionMode,
    MarketRegime,
    SignalType,
    VolatilityRegime,
)
from app.domains.strategy.contracts.context import MarketContext
from app.domains.strategy.tb002 import TB002Strategy
from app.domains.strategy.tb002.detector import ICTDetector
from app.domains.strategy.tb002.ict_primitives import (
    detect_sweep_of_high,
    fair_value_gaps,
    find_fvgs,
    swing_high_indices,
)

T0 = datetime(2026, 6, 30, 9, 15)


def _mk(seq, step=60):
    return [
        Candle(
            timestamp=T0 + timedelta(minutes=step * i), open=o, high=h, low=low, close=c
        )
        for i, (o, h, low, c) in enumerate(seq)
    ]


# ----------------------------------------------------------------------
# Primitives
# ----------------------------------------------------------------------
def test_find_bullish_and_bearish_fvg():
    # Bullish gap: candle0.high (10) < candle2.low (15) around middle index 1.
    bull = _mk([(9, 10, 8, 9), (10, 14, 9, 13), (15, 18, 15, 17)])
    gaps = find_fvgs(bull)
    assert len(gaps) == 1 and gaps[0].direction == "BULLISH"
    assert gaps[0].low == 10 and gaps[0].high == 15

    # Bearish gap: candle0.low (15) > candle2.high (10).
    bear = _mk([(16, 17, 15, 16), (14, 15, 11, 12), (10, 10, 7, 8)])
    gaps = find_fvgs(bear)
    assert len(gaps) == 1 and gaps[0].direction == "BEARISH"


def test_fvg_inversion_marked():
    # Bullish FVG at idx1; later candle closes below its low -> inverted.
    candles = _mk([(9, 10, 8, 9), (10, 14, 9, 13), (15, 18, 15, 17), (15, 16, 9, 9)])
    gaps = fair_value_gaps(candles)
    bull = [g for g in gaps if g.direction == "BULLISH"][0]
    assert bull.inverted is True
    assert bull.candles_to_invert == 2


def test_swing_high_and_sweep():
    candles = _mk(
        [
            (10, 12, 9, 11),
            (11, 15, 10, 14),
            (14, 20, 13, 19),
            (19, 18, 16, 17),
            (17, 19, 16, 18),
            (18, 25, 17, 18),
        ]  # idx5 high 25 sweeps idx2 high 20
    )
    highs = swing_high_indices(candles)
    assert 2 in highs  # swing high needs >= `left` candles to its left
    sweep = detect_sweep_of_high(candles, 2)
    assert sweep is not None and sweep.side == "BUY_SIDE"


# ----------------------------------------------------------------------
# Detector + TB002 round trip
# ----------------------------------------------------------------------
def _bearish_scenario():
    htf = _mk(
        [
            (24850, 24880, 24840, 24870),
            (24870, 24930, 24860, 24920),
            (24920, 25000, 24910, 24990),
            (24990, 24995, 24900, 24910),
            (24910, 24930, 24860, 24875),
            (24875, 24950, 24870, 24945),
            (24945, 25030, 24940, 24960),
            (24960, 24975, 24950, 24955),
            (24955, 24980, 24950, 24975),
            (24975, 25000, 24978, 24995),
            (24995, 24998, 24930, 24940),
            (24940, 24945, 24910, 24920),
            (24920, 24930, 24800, 24820),
            (24820, 24860, 24815, 24855),
            (24855, 24880, 24850, 24875),
        ]
    )
    m15 = _mk(
        [
            (25000, 25010, 24980, 24990),
            (24990, 24995, 24930, 24940),
            (24940, 24950, 24900, 24910),
            (24910, 24970, 24905, 24965),
            (24965, 24978, 24945, 24950),
            (24950, 24960, 24930, 24938),
            (24938, 24955, 24925, 24930),
            (24930, 24945, 24920, 24925),
        ],
        step=15,
    )
    ltf = _mk(
        [
            (24960, 24965, 24950, 24958),
            (24958, 24962, 24948, 24952),
            (24952, 24980, 24966, 24975),
            (24975, 24985, 24970, 24980),
            (24980, 24985, 24930, 24935),
        ],
        step=5,
    )
    return htf, m15, ltf


def test_detector_produces_valid_bearish_setup():
    htf, m15, ltf = _bearish_scenario()
    setup = ICTDetector().detect(
        htf=htf, m15=m15, ltf=ltf, now=datetime(2026, 6, 30, 11, 0)
    )
    assert setup is not None
    assert setup["direction"] == "BEARISH"
    # Geometry: stop above entry, target below, R:R >= 1.5.
    assert setup["stop_loss"] > setup["entry_price"]
    assert setup["external_target"] < setup["entry_price"]
    assert setup["sweep"]["side"] == "BUY_SIDE"
    assert setup["htf_inversion"]["candles_to_invert"] <= 2


def test_detected_setup_round_trips_through_tb002():
    htf, m15, ltf = _bearish_scenario()
    setup = ICTDetector().detect(
        htf=htf, m15=m15, ltf=ltf, now=datetime(2026, 6, 30, 11, 0)
    )
    assert setup is not None

    ctx = MarketContext(
        symbol="NIFTY",
        exchange="NSE",
        timeframe="5m",
        timestamp=datetime(2026, 6, 30, 11, 0),
        execution_mode=ExecutionMode.BACKTEST,
        last_price=setup["entry_price"],
        volatility_regime=VolatilityRegime.HIGH,
        market_regime=MarketRegime.REVERSAL,
        is_market_open=True,
    )
    ctx.metadata["tb002_setup"] = setup

    strategy = TB002Strategy()
    strategy.initialize()
    signal = strategy.generate_signal(ctx)

    assert signal is not None
    assert signal.signal_type is SignalType.SELL  # bearish -> short
    assert signal.confidence >= 0.70
    assert signal.score >= 1.5  # risk:reward


def test_detector_returns_none_on_flat_series():
    flat = _mk([(100, 101, 99, 100) for _ in range(20)])
    assert ICTDetector().detect(htf=flat, m15=flat, ltf=flat, now=T0) is None
