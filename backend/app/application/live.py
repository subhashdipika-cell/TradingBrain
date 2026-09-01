"""
TradingBrain
Application - Live Paper Trading Runner

Runs a strategy against a LIVE data feed with SIMULATED execution
(``PaperBroker``) - "live paper trading". This is the safe way to forward-test
with real market data and your Dhan token before risking capital: real ticks
in, simulated fills out, full risk engine + kill switch active.

The same ``TradingEngine`` loop powers backtest and live; here it is wrapped
with live logging and graceful shutdown. Swap ``PaperBroker`` for ``DhanBroker``
(dry_run=False) only when you are ready to trade real money.

Author: TradingBrain
"""

from __future__ import annotations

import logging
from datetime import datetime

from app.application.engine import EngineConfig, TradingEngine
from app.domains.analytics.journal import TradeJournal, TradeRecord
from app.domains.execution.broker import Broker
from app.domains.execution.feed import DataFeed
from app.domains.execution.paper_broker import PaperBroker
from app.domains.portfolio.portfolio import Portfolio
from app.domains.risk.limits import RiskLimits
from app.domains.risk.risk_engine import RiskEngine
from app.domains.shared.enums import ExecutionMode
from app.domains.strategy.contracts.strategy import BaseStrategy
from app.domains.strategy.tb001 import TB001Strategy

logger = logging.getLogger("tradingbrain.live")


class LoggingJournal(TradeJournal):
    """A journal that also streams events/trades to a logger as they happen."""

    def __init__(self, log: logging.Logger | None = None) -> None:
        super().__init__()
        self._log = log or logger

    def record_event(self, timestamp: datetime, message: str) -> None:
        super().record_event(timestamp, message)
        self._log.info("%s | %s", timestamp.isoformat(timespec="seconds"), message)

    def record_trade(self, trade: TradeRecord) -> None:
        super().record_trade(trade)
        self._log.info(
            "TRADE %s %s x%d pnl Rs %s (%s)",
            trade.structure,
            trade.symbol,
            trade.lots,
            f"{trade.pnl:,.0f}",
            trade.exit_reason,
        )


class LivePaperTrader:
    """Wraps the trading engine for live (or forward-test) runs."""

    def __init__(
        self, *, engine: TradingEngine, log: logging.Logger | None = None
    ) -> None:
        self.engine = engine
        self._log = log or logger

    def run(self) -> TradeJournal:
        """
        Run until the feed is exhausted or interrupted (Ctrl-C). Always
        returns the journal so results are inspectable after a stop.
        """
        self._log.info(
            "LivePaperTrader starting (mode=%s, equity Rs %s)",
            self.engine.config.execution_mode.value,
            f"{self.engine.portfolio.equity():,.0f}",
        )
        try:
            self.engine.run()
        except KeyboardInterrupt:  # pragma: no cover - interactive stop
            self._log.warning("Interrupted - flushing open positions to journal.")
        self._log.info(
            "LivePaperTrader stopped. Trades=%d, equity Rs %s",
            self.engine.journal.trade_count,
            f"{self.engine.portfolio.equity():,.0f}",
        )
        return self.engine.journal

    # ------------------------------------------------------------------
    @classmethod
    def build(
        cls,
        *,
        feed: DataFeed,
        broker: Broker | None = None,
        strategy: BaseStrategy | None = None,
        use_selector: bool = False,
        starting_capital: float = 1_000_000.0,
        bar_minutes: int = 1,
        execution_mode: ExecutionMode = ExecutionMode.PAPER,
        context_enricher=None,
        log: logging.Logger | None = None,
    ) -> "LivePaperTrader":
        """
        Assemble a live paper-trading stack around ``feed``.

        ``use_selector=True`` activates the regime-based selector so the engine
        picks the right strategy each bar (TB001 in calm regimes, TB002 in
        volatile/directional ones); otherwise a single ``strategy`` runs.
        ``context_enricher`` (e.g. a live ICT provider) is called each bar.
        """
        from app.domains.strategy.selector import default_selector

        selector = default_selector() if use_selector else None
        strat = None if use_selector else (strategy or TB001Strategy())

        engine = TradingEngine(
            strategy=strat,
            selector=selector,
            feed=feed,
            broker=broker or PaperBroker(),
            portfolio=Portfolio(starting_capital=starting_capital),
            risk_engine=RiskEngine(RiskLimits()),
            journal=LoggingJournal(log),
            config=EngineConfig(
                execution_mode=execution_mode,
                bar_minutes=bar_minutes,
            ),
            context_enricher=context_enricher,
        )
        return cls(engine=engine, log=log)

    @classmethod
    def from_dhan(
        cls,
        *,
        security_id: int,
        segment: str,
        client_id: str,
        access_token: str,
        symbol: str = "NIFTY",
        starting_capital: float = 1_000_000.0,
        use_selector: bool = True,
        strategy: BaseStrategy | None = None,
        max_polls: int | None = None,
        enable_ict: bool = True,
        today_gap_pct: float | None = None,
        log: logging.Logger | None = None,
    ) -> "LivePaperTrader":
        """
        Live paper trading on a Dhan feed (real data) with simulated fills.
        Regime-based strategy activation is on by default; ``enable_ict`` wires
        a live Dhan-candle ICT detector so TB002 can fire on real structure.
        When the single strategy is TB008, the feed also pulls the next-expiry
        chain (calendar) with a wider strike window. Requires ``dhanhq`` + token.
        ``today_gap_pct`` (from the Daily Brain's plan) is stamped onto every
        bar's context so entry sizing can react to an abnormal open.
        """
        from app.domains.execution.adapters.dhan_adapter import DhanFeed
        from app.domains.market.symbol import get_instrument

        # TB008 needs the next-expiry chain + far-OTM (~2-delta) strikes.
        is_calendar = strategy is not None and getattr(strategy, "name", "") == "TB008"

        spec = get_instrument(symbol)
        feed = DhanFeed(
            spec=spec,
            security_id=security_id,
            segment=segment,
            client_id=client_id,
            access_token=access_token,
            max_polls=max_polls,
            include_far=is_calendar,
            atm_range=40 if is_calendar else 5,
        )

        ict_enrich = None
        if enable_ict:
            from app.application.ict_live import DhanLiveICT

            ict_enrich = DhanLiveICT(
                security_id=security_id,
                exchange_segment=segment,
                instrument_type="INDEX",
                client_id=client_id,
                access_token=access_token,
                log=log,
            ).enrich

        def enricher(context):
            if ict_enrich is not None:
                ict_enrich(context)
            if today_gap_pct is not None:
                context.today_gap_pct = today_gap_pct

        return cls.build(
            feed=feed,
            strategy=strategy,
            use_selector=use_selector,
            starting_capital=starting_capital,
            execution_mode=ExecutionMode.PAPER,
            context_enricher=enricher,
            log=log,
        )
