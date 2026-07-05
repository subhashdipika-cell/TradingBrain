"""
TradingBrain
Execution - Historical Data Feed

Replays *stored* historical data (e.g. downloaded via the Dhan Data API by an
external tool) into the engine through the standard :class:`DataFeed`
interface. Two modes cover the realistic data shapes:

1. ``UnderlyingHistoricalFeed`` - you have underlying (index) OHLC only. The
   option chain is reconstructed per bar with Black-Scholes from the real spot
   plus an IV (a column if you have it, else a constant). Semi-synthetic, but
   driven by real price action.

2. ``OptionChainHistoricalFeed`` - you have per-strike option candles
   (real CE/PE premiums). These are replayed as the *actual* tradeable prices,
   with Greeks computed via Black-Scholes (using your IV column if present, or
   implied from the premium). This is the accurate path for straddle PnL.

The CSV loaders use only the standard library (no pandas) and accept a
configurable column map, so they adapt to whatever schema your downloader
writes. SQLite/Postgres loaders can be added the same way later.

Author: TradingBrain
"""

from __future__ import annotations

import csv
import glob
import os
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from app.domains.execution.feed import DataFeed, MarketSnapshot
from app.domains.market.candle import Candle
from app.domains.market.expiry import next_weekly_expiry, time_to_expiry_years
from app.domains.market.greeks import OptionGreeks, black_scholes, implied_volatility
from app.domains.market.option_chain import (
    OptionChain,
    OptionQuote,
    build_synthetic_chain,
)
from app.domains.market.symbol import InstrumentSpec
from app.domains.shared.enums import OptionRight


# ---------------------------------------------------------------------
# Column maps + parsing
# ---------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class CandleColumns:
    """Column names for an underlying-OHLC CSV."""

    timestamp: str = "timestamp"
    open: str = "open"
    high: str = "high"
    low: str = "low"
    close: str = "close"
    volume: str = "volume"
    iv: str | None = None  # optional implied-vol column (fraction)


@dataclass(frozen=True, slots=True)
class OptionColumns:
    """Column names for a per-strike option CSV."""

    timestamp: str = "timestamp"
    strike: str = "strike"
    right: str = "right"  # CE/PE/CALL/PUT
    close: str = "close"  # option premium
    underlying: str = "underlying"  # underlying spot at that time
    expiry: str | None = "expiry"  # ISO date; else weekly expiry is derived
    iv: str | None = None  # optional implied-vol column (fraction)


@dataclass(frozen=True, slots=True)
class DhanOptionColumns:
    """
    Column map for the Dhan option-chain snapshots written by AlphaEdge's
    ``dhan_options_collector`` (``..._OPT_*.csv``). IV is stored in percent and
    timestamps are UTC.
    """

    timestamp: str = "time"
    strike: str = "strike"
    right: str = "type"  # CE / PE
    premium: str = "ltp"
    underlying: str = "under_ltp"
    expiry: str = "expiry"
    iv: str = "iv"  # percent
    delta: str = "delta"
    theta: str = "theta"
    vega: str = "vega"


def parse_datetime(value: str, fmt: str | None = None) -> datetime:
    """Parse a timestamp from epoch seconds, ISO, or an explicit format."""
    value = value.strip()
    if fmt:
        return datetime.strptime(value, fmt)
    if value.isdigit():
        return datetime.fromtimestamp(int(value))
    return datetime.fromisoformat(value)


def _parse_right(value: str) -> OptionRight:
    token = value.strip().upper()
    if token in ("CE", "CALL", "C"):
        return OptionRight.CALL
    if token in ("PE", "PUT", "P"):
        return OptionRight.PUT
    raise ValueError(f"Unrecognized option right: {value!r}")


def load_candles(
    path: str,
    columns: CandleColumns = CandleColumns(),
    *,
    datetime_format: str | None = None,
) -> tuple[list[Candle], list[float | None]]:
    """Load underlying candles (and optional per-bar IV) from a CSV file."""
    candles: list[Candle] = []
    ivs: list[float | None] = []
    with open(path, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            candles.append(
                Candle(
                    timestamp=parse_datetime(row[columns.timestamp], datetime_format),
                    open=float(row[columns.open]),
                    high=float(row[columns.high]),
                    low=float(row[columns.low]),
                    close=float(row[columns.close]),
                    volume=float(row.get(columns.volume, 0) or 0),
                )
            )
            ivs.append(
                float(row[columns.iv]) if columns.iv and row.get(columns.iv) else None
            )
    return candles, ivs


# ---------------------------------------------------------------------
# Underlying-only feed (BS-reconstructed chain)
# ---------------------------------------------------------------------
class UnderlyingHistoricalFeed(DataFeed):
    """Replays underlying OHLC; reconstructs an option chain per bar."""

    def __init__(
        self,
        *,
        spec: InstrumentSpec,
        candles: list[Candle],
        ivs: list[float | None] | None = None,
        implied_vol: float = 0.12,
        rate: float = 0.065,
        expiry_weekday: int = 3,
        strikes_each_side: int = 10,
    ) -> None:
        if not candles:
            raise ValueError("UnderlyingHistoricalFeed requires candles.")
        self._spec = spec
        self._candles = candles
        self._ivs = ivs or [None] * len(candles)
        self._implied_vol = implied_vol
        self._rate = rate
        self._expiry_weekday = expiry_weekday
        self._strikes_each_side = strikes_each_side

    @property
    def spec(self) -> InstrumentSpec:
        return self._spec

    def stream(self) -> Iterator[MarketSnapshot]:
        for candle, iv_value in zip(self._candles, self._ivs):
            iv = iv_value if iv_value is not None else self._implied_vol
            expiry = next_weekly_expiry(candle.timestamp.date(), self._expiry_weekday)
            tte = time_to_expiry_years(candle.timestamp, expiry)
            chain = build_synthetic_chain(
                spec=self._spec,
                spot=candle.close,
                expiry=expiry,
                timestamp=candle.timestamp,
                time_to_expiry=tte,
                implied_vol=iv,
                rate=self._rate,
                strikes_each_side=self._strikes_each_side,
            )
            yield MarketSnapshot(
                timestamp=candle.timestamp,
                spec=self._spec,
                candle=candle,
                implied_vol=iv,
                expiry=expiry,
                time_to_expiry=tte,
                option_chain=chain,
            )

    @classmethod
    def from_csv(
        cls,
        path: str,
        *,
        spec: InstrumentSpec,
        columns: CandleColumns = CandleColumns(),
        datetime_format: str | None = None,
        **kwargs: object,
    ) -> "UnderlyingHistoricalFeed":
        candles, ivs = load_candles(path, columns, datetime_format=datetime_format)
        return cls(spec=spec, candles=candles, ivs=ivs, **kwargs)  # type: ignore[arg-type]


# ---------------------------------------------------------------------
# Real per-strike option feed
# ---------------------------------------------------------------------
@dataclass(slots=True)
class _OptionRow:
    timestamp: datetime
    strike: float
    right: OptionRight
    premium: float
    underlying: float
    expiry: date | None
    iv: float | None
    # Real per-unit greeks if the source provides them (e.g. Dhan).
    delta: float | None = None
    theta: float | None = None
    vega: float | None = None


class OptionChainHistoricalFeed(DataFeed):
    """Replays real per-strike option premiums as the tradeable prices."""

    def __init__(
        self,
        *,
        spec: InstrumentSpec,
        rows: list[_OptionRow],
        rate: float = 0.065,
        expiry_weekday: int = 3,
    ) -> None:
        if not rows:
            raise ValueError("OptionChainHistoricalFeed requires option rows.")
        self._spec = spec
        self._rows = sorted(rows, key=lambda r: r.timestamp)
        self._rate = rate
        self._expiry_weekday = expiry_weekday

    @property
    def spec(self) -> InstrumentSpec:
        return self._spec

    def stream(self) -> Iterator[MarketSnapshot]:
        for snapshot in self._group_into_snapshots():
            yield snapshot

    def _group_into_snapshots(self) -> Iterator[MarketSnapshot]:
        bucket: list[_OptionRow] = []
        current: datetime | None = None
        for row in self._rows:
            if current is not None and row.timestamp != current:
                yield self._build_snapshot(current, bucket)
                bucket = []
            current = row.timestamp
            bucket.append(row)
        if current is not None and bucket:
            yield self._build_snapshot(current, bucket)

    def _build_snapshot(
        self, timestamp: datetime, rows: list[_OptionRow]
    ) -> MarketSnapshot:
        spot = rows[0].underlying
        expiry = rows[0].expiry or next_weekly_expiry(
            timestamp.date(), self._expiry_weekday
        )
        tte = time_to_expiry_years(timestamp, expiry)

        chain = OptionChain(
            symbol=self._spec.symbol,
            underlying=spot,
            expiry=expiry,
            timestamp=timestamp,
        )
        ivs: list[float] = []
        for row in rows:
            iv = self._row_iv(row, tte)
            ivs.append(iv)
            greeks = self._greeks_for(row, tte, iv)
            chain.add(
                OptionQuote(
                    symbol=self._spec.symbol,
                    expiry=expiry,
                    strike=row.strike,
                    right=row.right,
                    greeks=greeks,
                    underlying=spot,
                )
            )

        candle = Candle(
            timestamp=timestamp,
            open=spot,
            high=spot,
            low=spot,
            close=spot,
        )
        avg_iv = sum(ivs) / len(ivs) if ivs else 0.0
        return MarketSnapshot(
            timestamp=timestamp,
            spec=self._spec,
            candle=candle,
            implied_vol=avg_iv,
            expiry=expiry,
            time_to_expiry=tte,
            option_chain=chain,
        )

    def _row_iv(self, row: _OptionRow, tte: float) -> float:
        if row.iv is not None:
            return row.iv
        return implied_volatility(
            right=row.right,
            market_price=row.premium,
            spot=row.underlying,
            strike=row.strike,
            time_to_expiry=tte,
            rate=self._rate,
        )

    def _greeks_for(self, row: _OptionRow, tte: float, iv: float) -> OptionGreeks:
        # Always keep the REAL premium as the tradeable price so PnL reflects
        # actual option values. For greeks, prefer source-provided values
        # (e.g. Dhan delta/theta/vega) and fill the rest from Black-Scholes.
        bs = black_scholes(
            right=row.right,
            spot=row.underlying,
            strike=row.strike,
            time_to_expiry=tte,
            volatility=max(iv, 1e-4),
            rate=self._rate,
        )
        return OptionGreeks(
            price=row.premium,
            delta=row.delta if row.delta is not None else bs.delta,
            gamma=bs.gamma,
            theta=row.theta if row.theta is not None else bs.theta,
            vega=row.vega if row.vega is not None else bs.vega,
            rho=bs.rho,
        )

    @classmethod
    def from_csv(
        cls,
        path: str,
        *,
        spec: InstrumentSpec,
        columns: OptionColumns = OptionColumns(),
        datetime_format: str | None = None,
        **kwargs: object,
    ) -> "OptionChainHistoricalFeed":
        rows: list[_OptionRow] = []
        with open(path, newline="", encoding="utf-8") as fh:
            for raw in csv.DictReader(fh):
                expiry: date | None = None
                if columns.expiry and raw.get(columns.expiry):
                    expiry = date.fromisoformat(raw[columns.expiry].strip())
                rows.append(
                    _OptionRow(
                        timestamp=parse_datetime(
                            raw[columns.timestamp], datetime_format
                        ),
                        strike=float(raw[columns.strike]),
                        right=_parse_right(raw[columns.right]),
                        premium=float(raw[columns.close]),
                        underlying=float(raw[columns.underlying]),
                        expiry=expiry,
                        iv=(
                            float(raw[columns.iv])
                            if columns.iv and raw.get(columns.iv)
                            else None
                        ),
                    )
                )
        return cls(spec=spec, rows=rows, **kwargs)  # type: ignore[arg-type]

    @classmethod
    def from_dhan_csv(
        cls,
        paths: str | list[str],
        *,
        spec: InstrumentSpec,
        columns: DhanOptionColumns = DhanOptionColumns(),
        tz_offset_minutes: int = 330,  # UTC -> IST (+5:30)
        iv_is_percent: bool = True,
        **kwargs: object,
    ) -> "OptionChainHistoricalFeed":
        """
        Load Dhan option-chain snapshots written by AlphaEdge
        (``..._OPT_*.csv``). Accepts a single path or a list of daily files
        (concatenated). Timestamps are shifted UTC->IST, IV is converted from
        percent to a fraction, and Dhan's real delta/theta/vega are kept.
        """
        if isinstance(paths, str):
            paths = [paths]

        offset = timedelta(minutes=tz_offset_minutes)
        rows: list[_OptionRow] = []
        for path in paths:
            with open(path, newline="", encoding="utf-8") as fh:
                for raw in csv.DictReader(fh):
                    iv_raw = raw.get(columns.iv)
                    iv = None
                    if iv_raw not in (None, ""):
                        iv = float(iv_raw)
                        if iv_is_percent:
                            iv /= 100.0
                    expiry: date | None = None
                    if raw.get(columns.expiry):
                        expiry = date.fromisoformat(raw[columns.expiry].strip())
                    rows.append(
                        _OptionRow(
                            timestamp=parse_datetime(raw[columns.timestamp]) + offset,
                            strike=float(raw[columns.strike]),
                            right=_parse_right(raw[columns.right]),
                            premium=float(raw[columns.premium]),
                            underlying=float(raw[columns.underlying]),
                            expiry=expiry,
                            iv=iv,
                            delta=_opt_float(raw.get(columns.delta)),
                            theta=_opt_float(raw.get(columns.theta)),
                            vega=_opt_float(raw.get(columns.vega)),
                        )
                    )
        return cls(spec=spec, rows=rows, **kwargs)  # type: ignore[arg-type]

    @classmethod
    def from_dhan_dir(
        cls,
        directory: str,
        *,
        spec: InstrumentSpec,
        prefix: str,
        **kwargs: object,
    ) -> "OptionChainHistoricalFeed":
        """
        Load all daily Dhan option files matching ``{prefix}_OPT_*.csv`` from a
        directory (e.g. AlphaEdge's ``strategy-lab/data/options``).
        """
        pattern = os.path.join(directory, f"{prefix}_OPT_*.csv")
        files = sorted(glob.glob(pattern))
        if not files:
            raise FileNotFoundError(f"No option files matching {pattern!r}.")
        return cls.from_dhan_csv(files, spec=spec, **kwargs)  # type: ignore[arg-type]


def _opt_float(value: str | None) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)  # type: ignore[arg-type]
    except ValueError:
        return None
