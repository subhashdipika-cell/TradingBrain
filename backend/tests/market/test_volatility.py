"""Focused tests for completed-data realized volatility."""

from __future__ import annotations

import math
from datetime import datetime, timedelta

from app.domains.market.candle import Candle
from app.domains.market.volatility import annualized_realized_volatility


def _candles(closes: list[float], *, start: datetime, minutes: int = 5) -> list[Candle]:
    return [
        Candle(
            timestamp=start + timedelta(minutes=index * minutes),
            open=close,
            high=close,
            low=close,
            close=close,
            volume=1.0,
        )
        for index, close in enumerate(closes)
    ]


def test_realized_volatility_requires_completed_return_history():
    candles = _candles([100.0 + index for index in range(20)], start=datetime(2026, 1, 2, 9, 15))

    assert annualized_realized_volatility(candles, bar_minutes=5) is None


def test_realized_volatility_annualizes_completed_log_returns():
    returns = [0.001, -0.001] * 11
    closes = [100.0]
    for value in returns:
        closes.append(closes[-1] * math.exp(value))
    candles = _candles(closes, start=datetime(2026, 1, 2, 9, 15))

    rv = annualized_realized_volatility(candles, bar_minutes=5)

    assert rv is not None
    assert 0.13 < rv < 0.15


def test_realized_volatility_excludes_overnight_gap():
    first = _candles(
        [100.0 * math.exp(0.001 * index) for index in range(22)],
        start=datetime(2026, 1, 2, 9, 15),
    )
    overnight = Candle(
        timestamp=datetime(2026, 1, 5, 9, 15),
        open=150.0,
        high=150.0,
        low=150.0,
        close=150.0,
        volume=1.0,
    )

    rv = annualized_realized_volatility([*first, overnight], bar_minutes=5)

    assert rv is not None
    assert rv < 1e-10
