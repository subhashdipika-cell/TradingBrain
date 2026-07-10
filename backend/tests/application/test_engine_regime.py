"""Tests for regime-based strategy activation and directional execution."""

from __future__ import annotations

from app.application.engine import EngineConfig, TradingEngine
from app.domains.execution.backtest_feed import BacktestFeed
from app.domains.execution.paper_broker import PaperBroker
from app.domains.portfolio.portfolio import Portfolio
from app.domains.risk.risk_engine import RiskEngine
from app.domains.shared.enums import OrderSide, PositionSide, SignalType
from app.domains.strategy.contracts.context import MarketContext
from app.domains.strategy.contracts.signal import Signal
from app.domains.strategy.contracts.strategy import BaseStrategy
from app.domains.strategy.selector import default_selector
from app.domains.strategy.tb001 import TB001Strategy


def _engine(strategy=None, selector=None, feed=None):
    return TradingEngine(
        strategy=strategy,
        selector=selector,
        feed=feed or BacktestFeed(num_days=8, bar_minutes=15, base_iv=0.13),
        broker=PaperBroker(),
        portfolio=Portfolio(1_000_000),
        risk_engine=RiskEngine(),
        config=EngineConfig(bar_minutes=15),
    )


def test_engine_with_selector_runs_range_seller_in_calm_regime():
    # Calm synthetic data (normal vol -> mostly RANGING) -> the structure
    # router activates the defined-risk range seller (Iron Condor / TB004)
    # most of the time; the realized random-walk path can still drift into
    # brief trending stretches over an 8-day window, routing a minority of
    # entries to the directional credit spreads (TB005/TB006) instead.
    journal = _engine(selector=default_selector()).run()
    assert journal.trade_count >= 1
    condor_trades = [t for t in journal.trades if t.strategy == "TB004"]
    assert condor_trades
    assert all(t.structure == "IRON_CONDOR" for t in condor_trades)
    assert len(condor_trades) >= len(journal.trades) / 2


class _Bullish(BaseStrategy):
    """Minimal strategy emitting one directional (long) signal per session."""

    name = "DIRBULL"
    version = "1.0.0"
    description = "test directional"

    def initialize(self) -> None:
        self.enabled = True
        self._fired = False

    def pre_market(self, context: MarketContext) -> None: ...

    def generate_signal(self, context: MarketContext) -> Signal | None:
        if self._fired:
            return None
        self._fired = True
        spot = context.last_price
        return Signal(
            strategy=self.name,
            symbol=context.symbol,
            signal_type=SignalType.BUY,
            side=OrderSide.BUY,
            position_side=PositionSide.LONG,
            entry_price=spot,
            stop_loss=spot - 80,
            take_profit=spot + 80,
            requested_risk=0.02,
        )

    def manage_position(self, context: MarketContext) -> Signal | None:
        return None

    def manage_risk(self, context: MarketContext) -> None: ...

    def post_market(self, context: MarketContext) -> None:
        self.reset()

    def reset(self) -> None:
        self._fired = False


def test_engine_executes_directional_long_option():
    journal = _engine(strategy=_Bullish()).run()
    assert journal.trade_count >= 1
    # Directional bullish signal -> long CALL (defined-risk debit).
    assert all(t.structure == "LONG_CALL" for t in journal.trades)
    assert all(t.strategy == "DIRBULL" for t in journal.trades)
    # Exits should be driven by the underlying target/stop (or square-off).
    assert all(
        t.exit_reason in {"TARGET", "STOP_LOSS", "TIME_EXIT"} for t in journal.trades
    )


class _Gated(_Bullish):
    """Only emits when an upstream enricher has injected the go-flag."""

    name = "GATED"

    def generate_signal(self, context: MarketContext) -> Signal | None:
        if not context.metadata.get("ict_ready"):
            return None
        return super().generate_signal(context)


def test_gap_day_dampens_hedged_entry_sizing():
    # Same deterministic feed both times (seed=42 default) so any lots
    # difference is caused only by the injected gap, not different market
    # data. today_gap_pct=1.0 (>= the 0.75% threshold) should halve the
    # allocation for TB001's hedged Iron Fly entries.
    def gap_enricher(context: MarketContext) -> None:
        context.today_gap_pct = 1.0

    plain = TradingEngine(
        strategy=TB001Strategy(),
        feed=BacktestFeed(num_days=3, bar_minutes=15, base_iv=0.13),
        broker=PaperBroker(),
        portfolio=Portfolio(1_000_000),
        risk_engine=RiskEngine(),
        config=EngineConfig(bar_minutes=15),
    ).run()

    gapped = TradingEngine(
        strategy=TB001Strategy(),
        feed=BacktestFeed(num_days=3, bar_minutes=15, base_iv=0.13),
        broker=PaperBroker(),
        portfolio=Portfolio(1_000_000),
        risk_engine=RiskEngine(),
        config=EngineConfig(bar_minutes=15),
        context_enricher=gap_enricher,
    ).run()

    assert plain.trade_count >= 1
    assert gapped.trade_count >= 1
    plain_lots = plain.trades[0].lots
    gapped_lots = gapped.trades[0].lots
    assert gapped_lots < plain_lots


def test_context_enricher_feeds_strategy():
    calls = {"n": 0}

    def enricher(context: MarketContext) -> None:
        calls["n"] += 1
        context.metadata["ict_ready"] = True  # simulate ICT setup injection

    engine = TradingEngine(
        strategy=_Gated(),
        feed=BacktestFeed(num_days=6, bar_minutes=15, base_iv=0.13),
        broker=PaperBroker(),
        portfolio=Portfolio(1_000_000),
        risk_engine=RiskEngine(),
        config=EngineConfig(bar_minutes=15),
        context_enricher=enricher,
    )
    journal = engine.run()
    assert calls["n"] > 0  # hook invoked each bar
    assert journal.trade_count >= 1  # gated strategy fired via injected metadata
