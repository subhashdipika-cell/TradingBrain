"""
TradingBrain
Execution - Backtest Feed

A self-contained synthetic NIFTY/BANKNIFTY feed for backtesting. It produces
intraday candles via a seeded geometric random walk and a mean-reverting
implied-volatility path, and builds a Black-Scholes option chain for every
bar. No external data or network is required, so a strategy can be exercised
end-to-end deterministically.

Replace this with a CSV/parquet loader or a live adapter when real data is
available - the engine only depends on the :class:`DataFeed` interface.

Author: TradingBrain
"""

from __future__ import annotations

import random
from collections.abc import Iterator
from datetime import date, datetime, timedelta

from app.domains.execution.feed import DataFeed, MarketSnapshot
from app.domains.market.candle import Candle
from app.domains.market.expiry import next_weekly_expiry, time_to_expiry_years
from app.domains.market.option_chain import build_synthetic_chain
from app.domains.market.session import NSE_SESSION
from app.domains.market.symbol import NIFTY, InstrumentSpec


class BacktestFeed(DataFeed):
    """Deterministic synthetic intraday feed for one underlying."""

    def __init__(
        self,
        *,
        spec: InstrumentSpec = NIFTY,
        start_date: date = date(2026, 1, 1),
        num_days: int = 20,
        bar_minutes: int = 5,
        start_spot: float = 25_000.0,
        annual_vol: float = 0.13,
        base_iv: float = 0.12,
        rate: float = 0.065,
        seed: int = 42,
        strikes_each_side: int = 10,
        include_far: bool = False,
    ) -> None:
        self._spec = spec
        self._start_date = start_date
        self._num_days = num_days
        self._bar_minutes = bar_minutes
        self._start_spot = start_spot
        self._annual_vol = annual_vol
        self._base_iv = base_iv
        self._rate = rate
        self._rng = random.Random(seed)
        self._strikes_each_side = strikes_each_side
        self._include_far = include_far

    @property
    def spec(self) -> InstrumentSpec:
        return self._spec

    # ------------------------------------------------------------------
    # Stream
    # ------------------------------------------------------------------
    def stream(self) -> Iterator[MarketSnapshot]:
        spot = self._start_spot
        iv = self._base_iv

        # Trading minutes per bar -> per-bar volatility (252 sessions, 375 min).
        bars_per_year = 252 * (375 / self._bar_minutes)
        bar_sigma = self._annual_vol / (bars_per_year**0.5)

        for trading_day in self._trading_days():
            expiry = next_weekly_expiry(trading_day)
            for moment in self._bar_times(trading_day):
                # Spot: geometric random walk.
                shock = self._rng.gauss(0.0, bar_sigma)
                prev_spot = spot
                spot = max(1.0, spot * (1.0 + shock))

                # IV: mean-revert toward base with small noise, clamp positive.
                iv += 0.05 * (self._base_iv - iv) + self._rng.gauss(0.0, 0.002)
                iv = max(0.03, iv)

                candle = self._make_candle(moment, prev_spot, spot)
                tte = time_to_expiry_years(moment, expiry)
                chain = build_synthetic_chain(
                    spec=self._spec,
                    spot=spot,
                    expiry=expiry,
                    timestamp=moment,
                    time_to_expiry=tte,
                    implied_vol=iv,
                    rate=self._rate,
                    strikes_each_side=self._strikes_each_side,
                )

                far_chain = None
                far_expiry = None
                far_tte = 0.0
                if self._include_far:
                    far_expiry = next_weekly_expiry(expiry + timedelta(days=1))
                    far_tte = time_to_expiry_years(moment, far_expiry)
                    far_chain = build_synthetic_chain(
                        spec=self._spec,
                        spot=spot,
                        expiry=far_expiry,
                        timestamp=moment,
                        time_to_expiry=far_tte,
                        implied_vol=iv,
                        rate=self._rate,
                        strikes_each_side=self._strikes_each_side,
                    )

                yield MarketSnapshot(
                    timestamp=moment,
                    spec=self._spec,
                    candle=candle,
                    implied_vol=iv,
                    expiry=expiry,
                    time_to_expiry=tte,
                    option_chain=chain,
                    far_chain=far_chain,
                    far_expiry=far_expiry,
                    far_time_to_expiry=far_tte,
                )

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _trading_days(self) -> Iterator[date]:
        emitted = 0
        day = self._start_date
        while emitted < self._num_days:
            if day.weekday() < 5:  # Mon-Fri
                emitted += 1
                yield day
            day += timedelta(days=1)

    def _bar_times(self, trading_day: date) -> Iterator[datetime]:
        start = datetime.combine(trading_day, NSE_SESSION.open_time)
        end = datetime.combine(trading_day, NSE_SESSION.close_time)
        moment = start
        step = timedelta(minutes=self._bar_minutes)
        while moment <= end:
            yield moment
            moment += step

    def _make_candle(self, moment: datetime, prev_close: float, close: float) -> Candle:
        high = max(prev_close, close) * (1.0 + abs(self._rng.gauss(0.0, 0.0005)))
        low = min(prev_close, close) * (1.0 - abs(self._rng.gauss(0.0, 0.0005)))
        return Candle(
            timestamp=moment,
            open=prev_close,
            high=high,
            low=low,
            close=close,
            volume=float(self._rng.randint(1000, 5000)),
        )
