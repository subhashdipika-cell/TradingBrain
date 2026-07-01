"""
TradingBrain
Market - Candle / OHLCV

Immutable OHLCV bar plus a small rolling series helper used to derive
simple indicators (range, returns) that feed the MarketContext.

Author: TradingBrain
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class Candle:
    """A single OHLCV bar."""

    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0

    @property
    def range(self) -> float:
        return self.high - self.low

    @property
    def body(self) -> float:
        return abs(self.close - self.open)

    @property
    def is_bullish(self) -> bool:
        return self.close >= self.open

    @property
    def typical_price(self) -> float:
        return (self.high + self.low + self.close) / 3.0


class CandleSeries:
    """A bounded rolling window of recent candles."""

    def __init__(self, maxlen: int = 500) -> None:
        self._candles: deque[Candle] = deque(maxlen=maxlen)

    def add(self, candle: Candle) -> None:
        self._candles.append(candle)

    def __len__(self) -> int:
        return len(self._candles)

    @property
    def last(self) -> Candle | None:
        return self._candles[-1] if self._candles else None

    def closes(self) -> list[float]:
        return [c.close for c in self._candles]

    def sma(self, period: int) -> float | None:
        """Simple moving average of close over ``period`` bars."""
        if len(self._candles) < period or period <= 0:
            return None
        window = list(self._candles)[-period:]
        return sum(c.close for c in window) / period

    def true_range(self) -> float | None:
        """True range of the latest bar vs. the prior close."""
        if len(self._candles) < 2:
            return None
        prev = self._candles[-2]
        curr = self._candles[-1]
        return max(
            curr.high - curr.low,
            abs(curr.high - prev.close),
            abs(curr.low - prev.close),
        )

    def atr(self, period: int = 14) -> float | None:
        """Average true range over ``period`` bars."""
        if len(self._candles) < period + 1:
            return None
        candles = list(self._candles)
        trs: list[float] = []
        for i in range(len(candles) - period, len(candles)):
            prev = candles[i - 1]
            curr = candles[i]
            trs.append(
                max(
                    curr.high - curr.low,
                    abs(curr.high - prev.close),
                    abs(curr.low - prev.close),
                )
            )
        return sum(trs) / period
