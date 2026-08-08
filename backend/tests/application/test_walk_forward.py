"""Tests for chronological walk-forward window construction."""

from __future__ import annotations

from datetime import date, timedelta

from app.application.walk_forward import WalkForwardConfig, build_walk_forward_windows


def _files(count: int) -> list[str]:
    # Dates are intentionally consecutive and already sorted in the names.
    start = date(2026, 6, 23)
    return [
        f"NIFTY50_OPT_{start + timedelta(days=i):%Y-%m-%d}.csv"
        for i in range(count)
    ]


def test_walk_forward_windows_are_chronological_and_non_leaking() -> None:
    windows = build_walk_forward_windows(
        _files(20), WalkForwardConfig(train_days=4, validation_days=2, test_days=2, step_days=2)
    )
    assert len(windows) == 7
    first = windows[0]
    assert first.train_files[-1] < first.validation_files[0]
    assert first.validation_files[-1] < first.test_files[0]
    assert first.test_files[0] == "NIFTY50_OPT_2026-06-29.csv"
    assert windows[1].train_files[0] == "NIFTY50_OPT_2026-06-25.csv"


def test_walk_forward_returns_no_partial_window() -> None:
    windows = build_walk_forward_windows(
        _files(7), WalkForwardConfig(train_days=3, validation_days=2, test_days=2, step_days=1)
    )
    assert len(windows) == 1
