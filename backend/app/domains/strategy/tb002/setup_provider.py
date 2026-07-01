"""
TradingBrain

TB002 - ICT Setup Provider

Bridges raw multi-timeframe candles to the :class:`ICTDetector` and writes the
resulting setup onto a ``MarketContext`` (``metadata["tb002_setup"]``) so TB002
can act on it. Includes:

- ``load_mt5_candles`` - read AlphaEdge MT5 OHLC CSVs (NIFTY/BANKNIFTY/...).
- ``resample`` - build a higher timeframe (e.g. 15m from 5m) by bucketing.
- ``ICTSetupProvider`` - hold candle series, detect, and enrich a context.

This is the data layer the TB002 model needs; wire it to a live candle feed
(MT5 bridge or Dhan intraday API) for forward testing.

Author: TradingBrain
"""

from __future__ import annotations

import csv
from datetime import datetime
from typing import Iterable

from app.domains.market.candle import Candle
from app.domains.strategy.contracts.context import MarketContext
from app.domains.strategy.tb002.detector import ICTDetector


def load_mt5_candles(path: str) -> list[Candle]:
    """
    Load an AlphaEdge MT5 OHLC CSV
    (columns: ``time,open,high,low,close,tick_volume,spread,real_volume``).
    """
    candles: list[Candle] = []
    with open(path, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            candles.append(
                Candle(
                    timestamp=_parse_time(row["time"]),
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                    volume=float(row.get("tick_volume", 0) or 0),
                )
            )
    return candles


def _parse_time(value: str) -> datetime:
    value = value.strip()
    if value.isdigit():
        return datetime.fromtimestamp(int(value))
    return datetime.fromisoformat(value.replace("T", " "))


def resample(candles: list[Candle], factor: int) -> list[Candle]:
    """Aggregate ``factor`` consecutive candles into one (e.g. 5m -> 15m)."""
    if factor <= 1:
        return list(candles)
    out: list[Candle] = []
    for i in range(0, len(candles) - factor + 1, factor):
        bucket = candles[i : i + factor]
        out.append(
            Candle(
                timestamp=bucket[0].timestamp,
                open=bucket[0].open,
                high=max(c.high for c in bucket),
                low=min(c.low for c in bucket),
                close=bucket[-1].close,
                volume=sum(c.volume for c in bucket),
            )
        )
    return out


class ICTSetupProvider:
    """Holds multi-timeframe candles and detects/serves TB002 setups."""

    def __init__(
        self,
        *,
        htf: Iterable[Candle] = (),
        m15: Iterable[Candle] = (),
        ltf: Iterable[Candle] = (),
        detector: ICTDetector | None = None,
        ltf_timeframe: str = "5m",
        htf_window: int = 120,
        m15_window: int = 120,
        ltf_window: int = 120,
    ) -> None:
        self.detector = detector or ICTDetector()
        self._ltf_tf = ltf_timeframe
        self._htf_window = htf_window
        self._m15_window = m15_window
        self._ltf_window = ltf_window
        self._htf = list(htf)
        self._m15 = list(m15)
        self._ltf = list(ltf)

    # ------------------------------------------------------------------
    def detect(self, now: datetime) -> dict | None:
        return self.detector.detect(
            htf=self._htf[-self._htf_window :],
            m15=self._m15[-self._m15_window :],
            ltf=self._ltf[-self._ltf_window :],
            now=now,
            ltf_timeframe=self._ltf_tf,
        )

    def enrich(self, context: MarketContext) -> MarketContext:
        """Detect a setup at ``context.timestamp`` and attach it to metadata."""
        setup = self.detect(context.timestamp)
        if setup is not None:
            context.metadata["tb002_setup"] = setup
        return context
