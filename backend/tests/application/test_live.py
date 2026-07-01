"""Tests for the live paper-trading runner (using a finite feed)."""

from __future__ import annotations

from datetime import datetime, timedelta

from app.application.live import LivePaperTrader, LoggingJournal
from app.domains.execution.historical_feed import OptionChainHistoricalFeed
from app.domains.market.greeks import black_scholes
from app.domains.market.symbol import NIFTY
from app.domains.shared.enums import OptionRight


def _write_dhan_csv(path):
    """A few intraday option-chain snapshots in the Dhan/AlphaEdge schema."""
    header = (
        "time,underlying,under_ltp,expiry,strike,type,ltp,oi,prev_oi,"
        "iv,volume,delta,theta,vega,bid,ask"
    )
    start = datetime(2026, 6, 30, 3, 46, 0)  # UTC -> 09:16 IST
    # 11 strikes around ATM (matches real Dhan +/-5), so Iron Fly wings exist.
    strikes = [25000.0 + (i - 5) * 50 for i in range(11)]
    lines = [header]
    for i in range(40):
        ts = (start + timedelta(minutes=i)).strftime("%Y-%m-%d %H:%M:%S")
        spot = 25000.0
        for k in strikes:
            for right, code in ((OptionRight.CALL, "CE"), (OptionRight.PUT, "PE")):
                px = black_scholes(
                    right=right,
                    spot=spot,
                    strike=k,
                    time_to_expiry=2 / 365,
                    volatility=0.13,
                ).price
                lines.append(
                    f"{ts},NIFTY50,{spot},2026-07-02,{k},{code},{px:.2f},"
                    f"100,90,13.0,5000,0.5,-30,7,{px:.2f},{px:.2f}"
                )
    path.write_text("\n".join(lines), encoding="utf-8")


def test_live_runner_executes_and_logs(tmp_path):
    csv_path = tmp_path / "NIFTY50_OPT_2026-06-30.csv"
    _write_dhan_csv(csv_path)

    feed = OptionChainHistoricalFeed.from_dhan_csv(str(csv_path), spec=NIFTY)
    trader = LivePaperTrader.build(feed=feed, starting_capital=1_000_000)

    journal = trader.run()

    assert isinstance(trader.engine.journal, LoggingJournal)
    assert journal.trade_count >= 1
    # Live runner uses PaperBroker -> simulated fills, real (replayed) data.
    assert any(m.startswith("ENTER") for _, m in journal.events)
    assert any(m.startswith("EXIT") for _, m in journal.events)
    # No dangling position after the (finite) feed ends.
    assert trader.engine.portfolio.has_open_positions is False
