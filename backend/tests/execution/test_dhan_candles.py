"""Tests for the Dhan candle response parser and live ICT wiring."""

from __future__ import annotations

from datetime import datetime, timezone

from app.domains.execution.adapters.dhan_adapter import (
    DhanCandleFeed,
    candles_from_response,
)


def _epoch(y, mo, d, h, mi):
    return int(datetime(y, mo, d, h, mi, tzinfo=timezone.utc).timestamp())


def test_candles_from_response_parses_and_shifts_to_ist():
    resp = {
        "status": "success",
        "data": {
            "open": [25000, 25010],
            "high": [25050, 25060],
            "low": [24990, 25000],
            "close": [25040, 25055],
            "volume": [1000, 1100],
            # 03:45 UTC -> 09:15 IST ; 03:50 UTC -> 09:20 IST
            "timestamp": [_epoch(2026, 6, 30, 3, 45), _epoch(2026, 6, 30, 3, 50)],
        },
    }
    candles = candles_from_response(resp)
    assert len(candles) == 2
    assert candles[0].timestamp.hour == 9 and candles[0].timestamp.minute == 15
    assert candles[0].close == 25040
    assert candles[1].timestamp.minute == 20


def test_candles_from_response_handles_failure():
    assert candles_from_response({"status": "failure", "remarks": "bad"}) == []
    assert candles_from_response(None) == []


def test_dhan_candle_feed_guarded_without_sdk():
    feed = DhanCandleFeed(
        security_id=13,
        exchange_segment="IDX_I",
        instrument_type="INDEX",
        client_id="c",
        access_token="t",
    )
    # dhanhq is not installed in CI -> clear, guarded error.
    try:
        feed.fetch_intraday(interval=5)
        raise AssertionError("expected RuntimeError without dhanhq")
    except RuntimeError as exc:
        assert "dhanhq" in str(exc)


def test_live_ict_enrich_is_safe_without_sdk():
    from app.application.ict_live import DhanLiveICT
    from app.domains.shared.enums import ExecutionMode
    from app.domains.strategy.contracts.context import MarketContext

    live = DhanLiveICT(client_id="c", access_token="t")
    ctx = MarketContext(
        symbol="NIFTY",
        exchange="NSE",
        timeframe="5m",
        timestamp=datetime(2026, 6, 30, 11, 0),
        execution_mode=ExecutionMode.PAPER,
    )
    # Refresh fails (no SDK) but enrich must degrade gracefully, not raise.
    live.enrich(ctx)
    assert "tb002_setup" not in ctx.metadata
