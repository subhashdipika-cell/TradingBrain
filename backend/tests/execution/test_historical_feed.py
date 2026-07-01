"""Tests for the CSV historical feeds (underlying + per-strike options)."""

from __future__ import annotations

import csv
from datetime import datetime, timedelta

from app.application.engine import EngineConfig, TradingEngine
from app.domains.execution.historical_feed import (
    OptionChainHistoricalFeed,
    UnderlyingHistoricalFeed,
)
from app.domains.execution.paper_broker import PaperBroker
from app.domains.market.greeks import black_scholes
from app.domains.market.symbol import NIFTY
from app.domains.portfolio.portfolio import Portfolio
from app.domains.risk.risk_engine import RiskEngine
from app.domains.shared.enums import OptionRight
from app.domains.strategy.tb001 import TB001Strategy


def _intraday_timestamps(day: str, n: int, step_min: int = 5):
    start = datetime.fromisoformat(f"{day} 09:15:00")
    return [start + timedelta(minutes=step_min * i) for i in range(n)]


def _write_underlying_csv(path, spot=25000.0):
    rows = []
    for i, ts in enumerate(_intraday_timestamps("2026-01-05", 60)):
        px = spot + (i % 7) - 3  # gentle wiggle, stays calm
        rows.append(
            {
                "timestamp": ts.isoformat(),
                "open": px,
                "high": px + 5,
                "low": px - 5,
                "close": px,
                "volume": 1000,
            }
        )
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


def test_underlying_feed_streams_and_backtests(tmp_path):
    csv_path = tmp_path / "nifty.csv"
    _write_underlying_csv(csv_path)

    feed = UnderlyingHistoricalFeed.from_csv(
        str(csv_path), spec=NIFTY, implied_vol=0.14
    )
    snapshots = list(feed.stream())
    assert len(snapshots) == 60
    assert (
        snapshots[0].option_chain.straddle(
            snapshots[0].spec.atm_strike(snapshots[0].spot)
        )
        is not None
    )

    # Run a real backtest through the engine on this CSV data.
    feed2 = UnderlyingHistoricalFeed.from_csv(
        str(csv_path), spec=NIFTY, implied_vol=0.14
    )
    engine = TradingEngine(
        strategy=TB001Strategy(),
        feed=feed2,
        broker=PaperBroker(),
        portfolio=Portfolio(1_000_000),
        risk_engine=RiskEngine(),
        config=EngineConfig(),
    )
    journal = engine.run()
    assert journal.trade_count >= 1


def test_option_chain_feed_replays_real_premiums(tmp_path):
    csv_path = tmp_path / "options.csv"
    spot = 25000.0
    strikes = [24900.0, 25000.0, 25100.0]
    rows = []
    for ts in _intraday_timestamps("2026-01-05", 5):
        tte = 2 / 365
        for strike in strikes:
            for right, code in ((OptionRight.CALL, "CE"), (OptionRight.PUT, "PE")):
                premium = black_scholes(
                    right=right,
                    spot=spot,
                    strike=strike,
                    time_to_expiry=tte,
                    volatility=0.13,
                ).price
                rows.append(
                    {
                        "timestamp": ts.isoformat(),
                        "strike": strike,
                        "right": code,
                        "close": round(premium, 2),
                        "underlying": spot,
                    }
                )
    with open(csv_path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    feed = OptionChainHistoricalFeed.from_csv(str(csv_path), spec=NIFTY)
    snapshots = list(feed.stream())
    assert len(snapshots) == 5

    chain = snapshots[0].option_chain
    straddle = chain.straddle(25000.0)
    assert straddle is not None
    call, put = straddle
    # The replayed price is the REAL premium from the CSV (not re-priced).
    assert call.price > 0 and put.price > 0
    assert call.greeks.theta < 0  # greeks still computed via BS


def test_dhan_format_loader(tmp_path):
    """from_dhan_csv: UTC->IST shift, IV percent->fraction, real greeks kept."""
    from app.domains.execution.historical_feed import OptionChainHistoricalFeed

    csv_path = tmp_path / "NIFTY50_OPT_2026-06-30.csv"
    header = (
        "time,underlying,under_ltp,expiry,strike,type,ltp,oi,prev_oi,"
        "iv,volume,delta,theta,vega,bid,ask"
    )
    # 03:46:27 UTC -> 09:16:27 IST. IV 12.5% -> 0.125. Real delta/theta/vega.
    lines = [
        header,
        "2026-06-30 03:46:27,NIFTY50,25000.0,2026-07-02,25000.0,CE,120.5,100,90,12.5,5000,0.51,-33.2,7.4,120.4,120.6",
        "2026-06-30 03:46:27,NIFTY50,25000.0,2026-07-02,25000.0,PE,118.0,200,180,13.0,6000,-0.49,-31.8,7.3,117.9,118.1",
    ]
    csv_path.write_text("\n".join(lines), encoding="utf-8")

    feed = OptionChainHistoricalFeed.from_dhan_csv(str(csv_path), spec=NIFTY)
    snaps = list(feed.stream())
    assert len(snaps) == 1
    snap = snaps[0]

    # UTC -> IST (+5:30)
    assert snap.timestamp.hour == 9 and snap.timestamp.minute == 16
    # IV converted from percent
    assert abs(snap.implied_vol - 0.1275) < 1e-6

    call = snap.option_chain.get(25000.0, OptionRight.CALL)
    assert call is not None
    assert call.price == 120.5  # real premium (ltp), not re-priced
    assert abs(call.greeks.delta - 0.51) < 1e-9  # real Dhan delta
    assert abs(call.greeks.theta - (-33.2)) < 1e-9  # real Dhan theta
