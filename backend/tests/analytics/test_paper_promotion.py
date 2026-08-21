"""Tests for the persisted PAPER-only strategy promotion gate."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

from app.application.results_store import ResultsStore
from app.domains.analytics.journal import TradeJournal, TradeRecord
from app.domains.analytics.paper_promotion import (
    PaperPromotionConfig,
    PaperPromotionTracker,
)


def _trade(day: int, pnl: float, *, strategy: str = "TB004") -> TradeRecord:
    timestamp = datetime(2026, 8, 1, 10, 0) + timedelta(days=day)
    return TradeRecord(
        strategy=strategy,
        symbol="NIFTY",
        structure="IRON_CONDOR",
        entry_time=timestamp,
        exit_time=timestamp + timedelta(hours=1),
        entry_value=1_000.0,
        exit_value=900.0,
        pnl=pnl,
        commission=25.0,
        exit_reason="TARGET" if pnl > 0 else "STOP_LOSS",
        lots=1,
    )


def _config(**overrides: object) -> PaperPromotionConfig:
    values = {
        "min_trades": 4,
        "min_sessions": 4,
        "min_profitable_session_rate": 0.5,
        "min_expectancy": 0.0,
        "min_profit_factor": 1.2,
        "max_drawdown_pct": 0.05,
        "max_single_loss_pct": 0.01,
    }
    values.update(overrides)
    return PaperPromotionConfig(**values)


def test_profitable_evidence_can_only_promote_paper_scaling(tmp_path: Path) -> None:
    tracker = PaperPromotionTracker(str(tmp_path / "promotion.json"), _config())
    journal = TradeJournal(
        trades=[_trade(0, 300), _trade(1, -100), _trade(2, 300), _trade(3, -100)]
    )

    assert tracker.ingest_journal("forward-1", journal, starting_capital=100_000) == 4
    assert tracker.ingest_journal("forward-1", journal, starting_capital=100_000) == 0

    decision = tracker.decisions()[0]
    assert decision.status == "PAPER_PROMOTED"
    assert decision.approved_for_paper_scaling
    assert not decision.live_authorized
    assert decision.profit_factor == 3.0
    assert decision.profitable_session_rate == 0.5

    restored = PaperPromotionTracker(str(tmp_path / "promotion.json"), _config())
    assert restored.decisions()[0] == decision


def test_tail_loss_blocks_promotion_even_after_recovery(tmp_path: Path) -> None:
    tracker = PaperPromotionTracker(str(tmp_path / "promotion.json"), _config())
    journal = TradeJournal(
        trades=[_trade(0, -1_500), _trade(1, 1_000), _trade(2, 1_000), _trade(3, 1_000)]
    )
    tracker.ingest_journal("forward-2", journal, starting_capital=100_000)

    decision = tracker.decisions()[0]
    assert not decision.approved_for_paper_scaling
    assert "largest loss 1.5% > 1.0%" in decision.reasons


def test_results_store_excludes_backtests_from_promotion(tmp_path: Path) -> None:
    store = ResultsStore(str(tmp_path / "results"))
    journal = TradeJournal(trades=[_trade(0, 100)])
    params = {"starting_capital": 100_000}

    store.save(
        run_type="backtest", symbol="NIFTY", journal=journal,
        report="backtest", params=params,
    )
    assert store.paper_promotion_tracker.decisions() == ()

    store.save(
        run_type="forward-test", symbol="NIFTY", journal=journal,
        report="paper", params=params,
    )
    decision = store.paper_promotion_tracker.decisions()[0]
    assert decision.trades == 1
    assert not decision.live_authorized
    json.dumps(store.paper_promotion_tracker.report(), allow_nan=False)
