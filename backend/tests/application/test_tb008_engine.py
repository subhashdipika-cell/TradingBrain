"""End-to-end: TB008 double calendar executed through the engine."""

from __future__ import annotations

from app.application.engine import EngineConfig, TradingEngine
from app.domains.execution.backtest_feed import BacktestFeed
from app.domains.execution.paper_broker import PaperBroker
from app.domains.portfolio.portfolio import Portfolio
from app.domains.risk.limits import RiskLimits
from app.domains.risk.risk_engine import RiskEngine
from app.domains.strategy.tb008 import TB008Strategy


def _engine():
    # Calm, low-IV feed with a next-expiry chain and wide strikes so the
    # ~2-delta legs and ratio hedges exist. Big capital so the ~Rs 2L margin
    # fits comfortably.
    feed = BacktestFeed(
        num_days=6,
        bar_minutes=15,
        base_iv=0.11,
        annual_vol=0.07,
        include_far=True,
        strikes_each_side=45,
        seed=5,
    )
    return TradingEngine(
        strategy=TB008Strategy(),
        feed=feed,
        broker=PaperBroker(),
        portfolio=Portfolio(2_000_000),
        risk_engine=RiskEngine(RiskLimits(max_capital_per_trade=1.0)),
        config=EngineConfig(bar_minutes=15),
    )


def test_tb008_executes_double_calendar_through_engine():
    journal = _engine().run()
    assert journal.trade_count >= 1
    assert all(t.structure == "DOUBLE_CALENDAR" for t in journal.trades)
    assert all(t.strategy == "TB008" for t in journal.trades)
    # Exits are PnL-target / stop / square-off driven.
    assert all(
        t.exit_reason in {"TARGET", "STOP_LOSS", "TIME_EXIT", "KILL_SWITCH"}
        for t in journal.trades
    )
    # An ENTER event names the double calendar and its margin.
    assert any(m.startswith("ENTER DOUBLE_CALENDAR") for _, m in journal.events)
    # No dangling positions after the run.
    assert journal.trade_count == sum(
        1 for _, m in journal.events if m.startswith("EXIT")
    )
