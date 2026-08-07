"""End-to-end backtest integration tests."""

from __future__ import annotations

from app.application.backtest import BacktestConfig, run_backtest


def test_backtest_runs_and_produces_trades():
    result = run_backtest(BacktestConfig(num_days=10, seed=42))
    journal = result.journal
    assert journal.trade_count > 0
    assert len(journal.equity_curve) > 0
    assert isinstance(result.report, str) and "TB001 Backtest" in result.report


def test_backtest_is_deterministic():
    a = run_backtest(BacktestConfig(num_days=8, seed=1))
    b = run_backtest(BacktestConfig(num_days=8, seed=1))
    assert a.journal.pnls() == b.journal.pnls()


def test_backtest_closes_all_positions_by_end():
    result = run_backtest(BacktestConfig(num_days=10, seed=3))
    # Every entry event must be matched by an exit (no dangling positions).
    entries = sum(1 for _, m in result.journal.events if m.startswith("ENTER"))
    exits = sum(1 for _, m in result.journal.events if m.startswith("EXIT"))
    assert entries == exits
    assert entries == result.journal.trade_count


def test_drawdown_respects_kill_switch_limit():
    # Realized vol >> implied: strategy bleeds, but the kill switch must cap
    # the drawdown near the configured 10% limit (with a small overshoot).
    result = run_backtest(
        BacktestConfig(num_days=40, base_iv=0.10, annual_vol=0.30, seed=11)
    )
    from app.domains.analytics.performance import compute_performance

    perf = compute_performance(result.journal.equity_values())
    assert perf.max_drawdown_pct <= 0.15
