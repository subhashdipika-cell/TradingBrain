"""Tests for time-window aggregation and conservative promotion."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from app.domains.analytics.journal import TradeJournal, TradeRecord
from app.domains.analytics.time_window import PromotionConfig, TimeWindowTracker


def _trade(timestamp: datetime, pnl: float) -> TradeRecord:
    return TradeRecord(
        strategy="TB004", symbol="BANKNIFTY", structure="IRON_CONDOR",
        entry_time=timestamp, exit_time=timestamp, entry_value=0.0,
        exit_value=0.0, pnl=pnl, commission=10.0, exit_reason="TARGET", lots=1,
    )


def test_tracker_is_idempotent_and_requires_evidence(tmp_path: Path) -> None:
    tracker = TimeWindowTracker(
        str(tmp_path / "time_windows.json"),
        PromotionConfig(min_trades=2, min_sessions=2, min_profit_factor=1.0),
    )
    journal = TradeJournal(trades=[
        _trade(datetime(2026, 8, 10, 14, 5), 100),
        _trade(datetime(2026, 8, 11, 14, 10), 100),
    ])
    assert tracker.ingest_journal("run-1", journal) == 2
    assert tracker.ingest_journal("run-1", journal) == 0
    decision = tracker.decisions("BANKNIFTY")[0]
    assert decision.approved
    assert tracker.allow_entry("BANKNIFTY", datetime(2026, 8, 12, 14, 15))


def test_unpromoted_window_does_not_block_entries(tmp_path: Path) -> None:
    tracker = TimeWindowTracker(str(tmp_path / "time_windows.json"))
    tracker.record_trade(
        _trade(datetime(2026, 8, 10, 10, 5), -100), trade_id="one"
    )
    assert tracker.allow_entry("BANKNIFTY", datetime(2026, 8, 12, 14, 15))
