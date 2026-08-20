"""
TradingBrain
Application - Trading Engine

The orchestrator. It drives the full trade lifecycle bar-by-bar:

    feed -> MarketContext -> strategy -> risk -> broker -> portfolio -> journal

The engine is execution-agnostic: give it a backtest feed + paper broker for
research, or a live feed + live broker for production - the loop is identical.
It owns the *mechanics* of a multi-leg option structure (sizing, leg fills,
target/stop/square-off exits); the strategy owns the *decisions* (when to
enter and with what thresholds).

Author: TradingBrain
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime, time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.domains.strategy.selector import StrategySelector

from app.domains.analytics.journal import TradeJournal, TradeRecord
from app.domains.execution.broker import Broker, Order
from app.domains.execution.feed import DataFeed, MarketSnapshot
from app.domains.market.indicators import analyse
from app.domains.market.session import NSE_SESSION, TradingSession
from app.domains.market.volatility import annualized_realized_volatility
from app.domains.portfolio.portfolio import Portfolio
from app.domains.risk.position_sizing import PositionSizer, SizingResult
from app.domains.risk.risk_engine import RiskEngine
from app.domains.shared.enums import (
    ExecutionMode,
    ExitReason,
    OptionRight,
    OptionStructure,
    PositionSide,
    VolatilityRegime,
)
from app.domains.strategy.contracts.context import MarketContext
from app.domains.strategy.contracts.signal import Signal
from app.domains.strategy.contracts.strategy import BaseStrategy


# No NEW entries at/after this time (IST session time) — trades are squared
# off at 15:15 (strategy configs), so later entries would be near-instant exits.
ENTRY_CUTOFF = time(15, 5)


@dataclass(frozen=True, slots=True)
class EngineConfig:
    """Engine-level execution settings."""

    execution_mode: ExecutionMode = ExecutionMode.BACKTEST
    bar_minutes: int = 5
    capital_allocation: float = 0.33
    margin_pct: float = 0.12
    record_equity_each_bar: bool = True


@dataclass(slots=True)
class _Leg:
    """One leg of an open structure."""

    instrument: str
    right: OptionRight
    strike: float
    side: str  # "BUY" (hedge/long) or "SELL" (write/short)
    lots: int = 0  # per-leg lots (calendar legs carry their own ratio)
    bucket: str = "near"  # "near" or "far" expiry (calendar strategies)


@dataclass(slots=True)
class _OpenTrade:
    """Engine bookkeeping for one open option structure (credit or debit)."""

    structure: str
    symbol: str
    body_strike: float
    lots: int
    units: int
    entry_time: datetime
    entry_credit: float  # per-unit NET credit (CREDIT) / -debit paid (DEBIT)
    target_credit: float  # per-unit cost-to-close target (CREDIT only)
    stop_credit: float  # per-unit cost-to-close stop (CREDIT only)
    square_off: time
    realized_start: float  # portfolio realized PnL captured before entry
    entry_commission: float = 0.0  # transaction costs paid on entry
    legs: list[_Leg] = field(default_factory=list)
    # Trade kind + attribution
    kind: str = "CREDIT"  # "CREDIT" (Iron Fly/straddle) or "DEBIT" (long option)
    strategy_name: str = "TB001"
    # Directional (DEBIT) exits are driven by the underlying spot levels.
    underlying_stop: float | None = None
    underlying_target: float | None = None
    # Calendar (CALENDAR) exits are driven by absolute rupee PnL vs margin.
    margin: float = 0.0
    profit_target: float = 0.0  # rupees; bank and leave
    max_loss_rupees: float = 0.0  # rupees; hard stop
    short_entry_premiums: dict[tuple[OptionRight, float], float] = field(default_factory=dict)
    short_stop_multiple: float = 1.5


class TradingEngine:
    """Bar-driven trade lifecycle orchestrator."""

    def __init__(
        self,
        *,
        strategy: BaseStrategy | None = None,
        feed: DataFeed,
        broker: Broker,
        portfolio: Portfolio,
        risk_engine: RiskEngine,
        selector: "StrategySelector | None" = None,
        sizer: PositionSizer | None = None,
        journal: TradeJournal | None = None,
        config: EngineConfig | None = None,
        session: TradingSession = NSE_SESSION,
        context_enricher: Callable[[MarketContext], None] | None = None,
        time_window_gate=None,
    ) -> None:
        if strategy is None and selector is None:
            raise ValueError("Provide either a strategy or a selector.")
        self.strategy = strategy
        self.selector = selector
        # Optional hook to enrich context each bar (e.g. inject an ICT setup
        # from candle data into metadata["tb002_setup"]).
        self.context_enricher = context_enricher
        self.time_window_gate = time_window_gate
        self.feed = feed
        self.broker = broker
        self.portfolio = portfolio
        self.risk = risk_engine
        self.sizer = sizer or PositionSizer(
            default_margin_pct=(config or EngineConfig()).margin_pct
        )
        self.journal = journal or TradeJournal()
        self.config = config or EngineConfig()
        self.session = session

        self._open_trade: _OpenTrade | None = None
        self._position_strategy: BaseStrategy | None = None
        self._current_day: date | None = None
        self._recent_candles: list = []  # rolling window for structure indicators
        # A live Dhan poll can call the strategy several times per minute. Keep
        # the journal useful by recording each distinct skip at most once per
        # minute, instead of filling it with duplicate polling messages.
        self._last_entry_skip: dict[str, datetime] = {}

    # ------------------------------------------------------------------
    # Strategy resolution (single strategy or regime-based selector)
    # ------------------------------------------------------------------
    def _strategies(self) -> list[BaseStrategy]:
        if self.selector is not None:
            return self.selector.all_strategies()
        return [self.strategy] if self.strategy is not None else []

    def _select_for_entry(self, context: MarketContext) -> BaseStrategy | None:
        if self.selector is not None:
            return self.selector.select(context)  # also sets context.market_regime
        return self.strategy

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def run(self) -> TradeJournal:
        """Run the engine to exhaustion over the feed and return the journal."""
        for strat in self._strategies():
            strat.initialize()
        last: MarketSnapshot | None = None

        for snapshot in self.feed.stream():
            day = snapshot.timestamp.date()
            if day != self._current_day:
                if last is not None:
                    self._end_of_day(last)
                self._start_of_day(snapshot)
                self._current_day = day
            self._on_bar(snapshot)
            last = snapshot

        if last is not None:
            self._end_of_day(last)

        return self.journal

    # ------------------------------------------------------------------
    # Session boundaries
    # ------------------------------------------------------------------
    def _start_of_day(self, snapshot: MarketSnapshot) -> None:
        context = self._build_context(snapshot)
        for strat in self._strategies():
            strat.pre_market(context)
        self.risk.start_session_at(self.portfolio.equity(), snapshot.timestamp)
        self.journal.record_event(
            snapshot.timestamp, f"Session start (equity {self.portfolio.equity():,.0f})"
        )

    def _end_of_day(self, snapshot: MarketSnapshot) -> None:
        if self._open_trade is not None:
            self._close_position(snapshot, ExitReason.TIME_EXIT)
        context = self._build_context(snapshot)
        for strat in self._strategies():
            strat.post_market(context)
        self.journal.record_equity(snapshot.timestamp, self.portfolio.equity())

    # ------------------------------------------------------------------
    # Per-bar processing
    # ------------------------------------------------------------------
    def _on_bar(self, snapshot: MarketSnapshot) -> None:
        context = self._build_context(snapshot)
        if self.context_enricher is not None:
            self.context_enricher(context)
        self._mark_portfolio(snapshot)

        if self.config.record_equity_each_bar:
            self.journal.record_equity(snapshot.timestamp, self.portfolio.equity())

        # Continuous account-level risk monitoring.
        decision = self.risk.update(self.portfolio, snapshot.timestamp)
        if decision.kill_switch_tripped:
            self.broker.cancel_pending()
            if self._open_trade is not None:
                self._close_position(snapshot, ExitReason.KILL_SWITCH)
            self.journal.record_event(
                snapshot.timestamp, f"KILL SWITCH: {decision.reason}"
            )
            return

        if self._open_trade is None:
            # Platform-wide intraday entry cutoff: no NEW positions at/after
            # 15:05 — every structure is squared off by 15:15, ahead of the
            # 15:30 NSE close, so a late entry would be closed almost at once.
            if snapshot.timestamp.time() >= ENTRY_CUTOFF:
                return
            active = self._select_for_entry(context)
            if active is None:
                self._record_entry_skip(
                    snapshot.timestamp,
                    context,
                    context.metadata.get(
                        "entry_rejection", "no strategy mapped for current regime"
                    ),
                )
                return  # regime has no strategy mapped -> sit out
            signal = active.generate_signal(context)
            if signal is not None and signal.is_entry:
                self._open_position(signal, snapshot, active)
            else:
                self._record_entry_skip(
                    snapshot.timestamp,
                    context,
                    context.metadata.get("entry_rejection", "strategy produced no entry signal"),
                    strategy=active.name,
                )
        else:
            self._manage_open_trade(snapshot, context)

    def _record_entry_skip(
        self,
        timestamp: datetime,
        context: MarketContext,
        reason: object,
        *,
        strategy: str | None = None,
    ) -> None:
        """Journal actionable no-entry diagnostics with a one-minute throttle."""
        text = str(reason)
        key = f"{context.symbol}|{strategy or 'AUTO'}|{text}"
        previous = self._last_entry_skip.get(key)
        if previous is not None and (timestamp - previous).total_seconds() < 60:
            return
        self._last_entry_skip[key] = timestamp
        regime = getattr(context.market_regime, "value", context.market_regime)
        vol = getattr(context.volatility_regime, "value", context.volatility_regime)
        self.journal.record_event(
            timestamp,
            f"ENTRY SKIP {context.symbol} {strategy or 'AUTO'}: {text} "
            f"(regime={regime}, vol={vol}, iv={context.implied_volatility:.3f}, "
            f"window={context.minutes_from_open}m)",
        )

    # ------------------------------------------------------------------
    # Position lifecycle
    # ------------------------------------------------------------------
    def _open_position(
        self, signal: Signal, snapshot: MarketSnapshot, strategy: BaseStrategy
    ) -> None:
        meta = signal.metadata
        if isinstance(meta.get("calendar_legs"), list) and meta["calendar_legs"]:
            # Two-expiry calendar structure (TB008).
            self._open_calendar(signal, snapshot, strategy)
            return
        leg_specs = meta.get("legs")
        if not isinstance(leg_specs, list) or not leg_specs:
            # No explicit legs -> treat a directional signal as a long option
            # (defined risk debit). This is how TB002's directional ICT view
            # is expressed as an options trade.
            self._open_directional(signal, snapshot, strategy)
            return

        spec = snapshot.spec
        leg_specs = [dict(ls) for ls in leg_specs]
        proposed_orders = [
            Order(
                symbol=spec.symbol,
                instrument=self._instrument(
                    spec.symbol, float(ls["strike"]), self._right(ls["right"])
                ),
                quantity=1 if str(ls.get("side", "")).upper() == "BUY" else -1,
                right=self._right(ls["right"]),
                strike=float(ls["strike"]),
                tag=f"{strategy.name}_RISK_PREVIEW",
            )
            for ls in leg_specs
        ]
        body_strike = float(meta.get("body_strike", 0.0))
        entry_credit = float(meta.get("entry_credit", 0.0))
        wing_width = meta.get("wing_width")  # None when naked

        # Every option-selling structure must identify a protective long leg
        # for each short right. This check runs before any broker call.
        pairs: list[tuple[OptionRight, float, float]] = []
        for right in (OptionRight.CALL, OptionRight.PUT):
            shorts = [
                float(ls["strike"])
                for ls in leg_specs
                if str(ls.get("side", "")).upper() == "SELL"
                and self._right(ls["right"]) is right
            ]
            longs = [
                float(ls["strike"])
                for ls in leg_specs
                if str(ls.get("side", "")).upper() == "BUY"
                and self._right(ls["right"]) is right
            ]
            if shorts and not longs:
                self.journal.record_event(
                    snapshot.timestamp,
                    f"Entry blocked: naked {right.value} short has no hedge",
                )
                strategy.reset()
                return
            if shorts and longs:
                pairs.append((right, shorts[0], max(longs, key=lambda strike: abs(strike - shorts[0]))))

        if any(str(ls.get("side", "")).upper() == "SELL" for ls in leg_specs) and not pairs:
            self.journal.record_event(snapshot.timestamp, "Entry blocked: unhedged option sale")
            strategy.reset()
            return

        if pairs:
            _, risk_short, risk_long = max(
                pairs, key=lambda pair: abs(pair[2] - pair[1])
            )
            gate = self.risk.portfolio_gate.validate_and_scale_order(
                self.portfolio,
                strategy_type=str(meta.get("structure", "CREDIT_SPREAD")),
                symbol=spec.symbol,
                short_strike=risk_short,
                long_strike=risk_long,
                # A 10% credit haircut protects sizing from a worse fill than
                # the strategy's indicative premium.
                net_credit=max(entry_credit * 0.90, 0.0),
                lot_size=spec.lot_size,
                when=snapshot.timestamp,
            )
            if not gate.approved:
                self.journal.record_event(
                    snapshot.timestamp, f"Entry blocked: {gate.reason}"
                )
                strategy.reset()
                return

            # Bring all protective wings inside the same fixed-fractional risk
            # envelope. The selector still chooses the initial strikes; the
            # risk gate may move a hedge closer, never farther away.
            for right, short, long in pairs:
                adjusted = self.risk.portfolio_gate.sizer.adjust_hedge_strike(
                    account_balance=self.portfolio.equity(),
                    short_strike=short,
                    long_strike=long,
                    net_credit=max(entry_credit * 0.90, 0.0),
                    symbol=spec.symbol,
                    lot_size=spec.lot_size,
                )
                for ls in leg_specs:
                    if (
                        str(ls.get("side", "")).upper() == "BUY"
                        and self._right(ls["right"]) is right
                        and float(ls["strike"]) == long
                    ):
                        ls["strike"] = adjusted

            sizing = SizingResult(
                lots=gate.safe_lot_count,
                units=gate.safe_lot_count * spec.lot_size,
                capital_used=gate.max_possible_loss,
                reason=gate.reason,
            )
        else:
            # Do not permit a premium-selling signal to fall back to the old
            # margin-only sizing path when it contains a short leg.
            if any(str(ls.get("side", "")).upper() == "SELL" for ls in leg_specs):
                self.journal.record_event(snapshot.timestamp, "Entry blocked: no defined-risk hedge")
                strategy.reset()
                return
            sizing = None

        legs = [
            _Leg(
                instrument=self._instrument(
                    spec.symbol, float(ls["strike"]), self._right(ls["right"])
                ),
                right=self._right(ls["right"]),
                strike=float(ls["strike"]),
                side=str(ls["side"]).upper(),
            )
            for ls in leg_specs
        ]

        # Sizing depends on the structure:
        # - Hedged (defined risk): size so MAX LOSS <= requested_risk x capital.
        #   The hedge both caps the loss and slashes margin (the point of the
        #   user's hedge-first rule), so risk - not margin - is the constraint.
        # - Naked: size by SPAN margin deployment (capital_allocation).
        if sizing is not None:
            max_loss_per_unit = max(float(wing_width or 0.0) - entry_credit, 1.0)
            margin_per_lot = max_loss_per_unit * spec.lot_size
        elif wing_width is not None:
            max_loss_per_unit = max(float(wing_width) - entry_credit, 1.0)
            margin_per_lot = max_loss_per_unit * spec.lot_size
            allocation = signal.requested_risk or self.config.capital_allocation
        else:
            margin_per_lot = self.sizer.margin_per_lot(
                spot=snapshot.spot, lot_size=spec.lot_size
            )
            allocation = self.config.capital_allocation

        if sizing is None:
            sizing = self.sizer.size_for_margin(
                capital=self.portfolio.capital.starting_capital,
                allocation_fraction=allocation,
                margin_per_lot=margin_per_lot,
                lot_size=spec.lot_size,
            )
        if not sizing.is_tradable:
            strategy.reset()
            return

        entry_gate = self.risk.approve_entry(
            self.portfolio,
            new_capital=sizing.capital_used,
            chain=snapshot.option_chain,
            proposed_orders=[
                Order(
                    symbol=order.symbol,
                    instrument=order.instrument,
                    quantity=order.quantity * sizing.units,
                    right=order.right,
                    strike=order.strike,
                    tag=order.tag,
                )
                for order in proposed_orders
            ],
        )
        if not entry_gate.approved:
            self.journal.record_event(
                snapshot.timestamp, f"Entry blocked: {entry_gate.reason}"
            )
            strategy.reset()
            return

        realized_start = self.portfolio.realized_pnl()

        # HEDGE-FIRST BASKET: order BUY (protective) legs before SELL (written)
        # legs and submit as one basket so the broker blocks only the reduced
        # spread margin.
        ordered = sorted(legs, key=lambda leg: 0 if leg.side == "BUY" else 1)
        orders = [
            Order(
                symbol=spec.symbol,
                instrument=leg.instrument,
                quantity=sizing.units if leg.side == "BUY" else -sizing.units,
                right=leg.right,
                strike=leg.strike,
                tag=f"{strategy.name}_ENTRY_{leg.side}",
            )
            for leg in ordered
        ]
        fills = self.broker.submit_basket(orders, snapshot)
        entry_commission = 0.0
        actual_entry_credit = 0.0
        short_entry_premiums: dict[tuple[OptionRight, float], float] = {}
        for fill in fills:
            self._book_fill(fill, fill.order.right, fill.order.strike)
            entry_commission += fill.commission
            if fill.order.quantity < 0 and fill.order.right is not None and fill.order.strike is not None:
                short_entry_premiums[(fill.order.right, fill.order.strike)] = fill.price
            actual_entry_credit += (
                -fill.quantity * fill.price / sizing.units
            )

        # A multi-leg option structure must be all-or-nothing. Roll back any
        # partial basket so a missing hedge or short leg cannot become a
        # phantom open trade or leave unbounded exposure.
        if len(fills) != len(orders) or any(
            abs(fill.quantity) != abs(fill.order.quantity) for fill in fills
        ):
            for fill in reversed(fills):
                rollback = self.broker.submit(
                    Order(
                        symbol=fill.order.symbol,
                        instrument=fill.order.instrument,
                        quantity=-fill.quantity,
                        right=fill.order.right,
                        strike=fill.order.strike,
                        expiry_bucket=fill.order.expiry_bucket,
                        tag=f"{strategy.name}_ENTRY_ROLLBACK",
                    ),
                    snapshot,
                )
                if rollback is not None:
                    self._book_fill(
                        rollback, rollback.order.right, rollback.order.strike
                    )
            strategy.reset()
            self.journal.record_event(
                snapshot.timestamp, "Entry cancelled: incomplete multi-leg fill"
            )
            return

        if actual_entry_credit <= 0.0:
            strategy.reset()
            return

        target_pct = float(meta.get("target_profit_pct", 0.30))
        stop_pct = float(meta.get("stop_loss_pct", 0.30))
        square_off = time.fromisoformat(str(meta.get("square_off_time", "15:15:00")))

        self._open_trade = _OpenTrade(
            structure=str(meta.get("structure", OptionStructure.IRON_FLY.value)),
            symbol=spec.symbol,
            body_strike=body_strike,
            lots=sizing.lots,
            units=sizing.units,
            entry_time=snapshot.timestamp,
            entry_credit=actual_entry_credit,
            target_credit=actual_entry_credit * (1.0 - target_pct),
            stop_credit=actual_entry_credit * (1.0 + stop_pct),
            square_off=square_off,
            realized_start=realized_start,
            entry_commission=entry_commission,
            legs=legs,
            kind="CREDIT",
            strategy_name=strategy.name,
            short_entry_premiums=short_entry_premiums,
            short_stop_multiple=max(float(meta.get("short_stop_multiple", 1.5)), 1.5),
        )
        self._position_strategy = strategy
        self.risk.record_trade()
        self.journal.record_event(
            snapshot.timestamp,
            f"ENTER {self._open_trade.structure} {spec.symbol} "
            f"{body_strike:.0f} x{sizing.lots} credit {actual_entry_credit:.2f}"
            + (f" (margin/lot Rs {margin_per_lot:,.0f})" if wing_width else ""),
        )

    def _open_directional(
        self, signal: Signal, snapshot: MarketSnapshot, strategy: BaseStrategy
    ) -> None:
        """
        Express a directional signal (TB002 ICT view) as a long option - a
        defined-risk debit: long CALL for a bullish/LONG signal, long PUT for a
        bearish/SHORT signal. Sized so the premium paid (the max loss) stays
        within ``requested_risk`` of capital.
        """
        spec = snapshot.spec
        bullish = signal.position_side is PositionSide.LONG
        right = OptionRight.CALL if bullish else OptionRight.PUT

        strike = snapshot.option_chain.nearest_strike(snapshot.spot)
        if strike is None:
            strategy.reset()
            return
        premium = snapshot.option_price(right, strike)
        if premium <= 0:
            strategy.reset()
            return

        risk_fraction = signal.requested_risk or 0.02
        budget = self.portfolio.capital.starting_capital * risk_fraction
        premium_per_lot = premium * spec.lot_size
        lots = int(budget // premium_per_lot)
        if lots <= 0:
            strategy.reset()
            return
        units = lots * spec.lot_size
        # Build the instrument before the risk preview. The preview order must
        # be identical to the order that will be sent, and using it before
        # assignment caused every directional signal to fail at runtime.
        instrument = self._instrument(spec.symbol, strike, right)

        gate = self.risk.approve_entry(
            self.portfolio,
            new_capital=premium_per_lot * lots,
            chain=snapshot.option_chain,
            proposed_orders=[
                Order(
                    symbol=spec.symbol,
                    instrument=instrument,
                    quantity=units,
                    right=right,
                    strike=strike,
                    tag=f"{strategy.name}_ENTRY_LONG",
                )
            ],
        )
        if not gate.approved:
            self.journal.record_event(
                snapshot.timestamp, f"Entry blocked: {gate.reason}"
            )
            strategy.reset()
            return

        realized_start = self.portfolio.realized_pnl()
        fill = self.broker.submit(
            Order(
                symbol=spec.symbol,
                instrument=instrument,
                quantity=units,  # long
                right=right,
                strike=strike,
                tag=f"{strategy.name}_ENTRY_LONG",
            ),
            snapshot,
        )
        if fill is None:
            strategy.reset()
            return
        self._book_fill(fill, right, strike)

        square_off = time(15, 15)
        self._open_trade = _OpenTrade(
            structure=(
                OptionStructure.LONG_CALL.value
                if bullish
                else OptionStructure.LONG_PUT.value
            ),
            symbol=spec.symbol,
            body_strike=strike,
            lots=lots,
            units=units,
            entry_time=snapshot.timestamp,
            entry_credit=-premium,  # debit
            target_credit=0.0,
            stop_credit=0.0,
            square_off=square_off,
            realized_start=realized_start,
            entry_commission=fill.commission,
            legs=[_Leg(instrument=instrument, right=right, strike=strike, side="BUY")],
            kind="DEBIT",
            strategy_name=strategy.name,
            underlying_stop=signal.stop_loss,
            underlying_target=signal.take_profit,
        )
        self._position_strategy = strategy
        self.risk.record_trade()
        self.journal.record_event(
            snapshot.timestamp,
            f"ENTER {self._open_trade.structure} {spec.symbol} {strike:.0f} "
            f"x{lots} debit {premium:.2f} (stop {signal.stop_loss}, "
            f"target {signal.take_profit})",
        )

    def _open_calendar(
        self, signal: Signal, snapshot: MarketSnapshot, strategy: BaseStrategy
    ) -> None:
        """
        Execute a two-expiry calendar structure (TB008). Near legs price/fill on
        the near chain, far legs on the next-expiry chain. The structure's own
        ratio is placed as-is, scaled by how many copies fit the margin budget.
        """
        meta = signal.metadata
        spec = snapshot.spec
        lot_size = spec.lot_size
        base_margin = float(meta.get("margin", 0.0))
        if base_margin <= 0:
            strategy.reset()
            return

        budget = self.portfolio.capital.starting_capital * (
            signal.requested_risk or self.config.capital_allocation
        )
        mult = int(budget // base_margin)
        if mult < 1:
            self.journal.record_event(
                snapshot.timestamp, "Calendar skipped: margin exceeds budget"
            )
            strategy.reset()
            return

        # Build legs; submit hedges (BUY) before writes (SELL).
        legs: list[_Leg] = []
        for spec_leg in meta["calendar_legs"]:
            right = self._right(spec_leg["right"])
            bucket = str(spec_leg.get("expiry_bucket", "near"))
            legs.append(
                _Leg(
                    instrument=self._instrument(
                        spec.symbol, float(spec_leg["strike"]), right, bucket
                    ),
                    right=right,
                    strike=float(spec_leg["strike"]),
                    side=str(spec_leg["side"]).upper(),
                    lots=int(spec_leg["lots"]) * mult,
                    bucket=bucket,
                )
            )

        # The near-expiry chain is available for the calendar's near legs. We
        # deliberately gate on those legs; the far hedge is additional
        # protection and must never be credited to make the near exposure look
        # safer than it is.
        near_orders = [
            Order(
                symbol=spec.symbol,
                instrument=leg.instrument,
                quantity=(leg.lots * lot_size if leg.side == "BUY" else -leg.lots * lot_size),
                right=leg.right,
                strike=leg.strike,
                expiry_bucket=leg.bucket,
                tag=f"{strategy.name}_RISK_PREVIEW",
            )
            for leg in legs if leg.bucket == "near"
        ]
        gate = self.risk.approve_entry(
            self.portfolio,
            new_capital=base_margin * mult,
            chain=snapshot.option_chain,
            proposed_orders=near_orders,
        )
        if not gate.approved:
            self.journal.record_event(
                snapshot.timestamp, f"Entry blocked: {gate.reason}"
            )
            strategy.reset()
            return

        realized_start = self.portfolio.realized_pnl()

        entry_commission = 0.0
        for leg in sorted(legs, key=lambda x: 0 if x.side == "BUY" else 1):
            units = leg.lots * lot_size
            fill = self.broker.submit(
                Order(
                    symbol=spec.symbol,
                    instrument=leg.instrument,
                    quantity=units if leg.side == "BUY" else -units,
                    right=leg.right,
                    strike=leg.strike,
                    expiry_bucket=leg.bucket,
                    tag=f"{strategy.name}_ENTRY_{leg.side}_{leg.bucket}",
                ),
                snapshot,
            )
            if fill is None:
                continue
            self._book_fill(fill, leg.right, leg.strike)
            entry_commission += fill.commission

        profit_target = float(meta.get("profit_target", 0.0)) * mult
        max_loss = abs(float(meta.get("max_loss", 0.0))) * mult

        self._open_trade = _OpenTrade(
            structure=str(meta.get("structure", "DOUBLE_CALENDAR")),
            symbol=spec.symbol,
            body_strike=snapshot.spot,
            lots=mult,
            units=0,
            entry_time=snapshot.timestamp,
            entry_credit=0.0,
            target_credit=0.0,
            stop_credit=0.0,
            square_off=time(15, 15),
            realized_start=realized_start,
            entry_commission=entry_commission,
            legs=legs,
            kind="CALENDAR",
            strategy_name=strategy.name,
            margin=base_margin * mult,
            profit_target=profit_target,
            max_loss_rupees=max_loss,
        )
        self._position_strategy = strategy
        self.risk.record_trade()
        self.journal.record_event(
            snapshot.timestamp,
            f"ENTER {self._open_trade.structure} {spec.symbol} x{mult} "
            f"(margin Rs {base_margin * mult:,.0f}, target Rs {profit_target:,.0f})",
        )

    def _manage_open_trade(
        self, snapshot: MarketSnapshot, context: MarketContext
    ) -> None:
        trade = self._open_trade
        assert trade is not None

        reason: ExitReason | None = None
        if trade.kind == "CALENDAR":
            unrealized = self.portfolio.unrealized_pnl()
            if unrealized >= trade.profit_target > 0:
                reason = ExitReason.TARGET
            elif trade.max_loss_rupees > 0 and unrealized <= -trade.max_loss_rupees:
                reason = ExitReason.STOP_LOSS
        elif trade.kind == "DEBIT":
            reason = self._directional_exit(snapshot, trade)
        else:
            if self._short_leg_stop_hit(snapshot, trade):
                reason = ExitReason.STOP_LOSS
            if reason is not None:
                self._close_position(snapshot, reason)
                return
            cost_to_close = self._cost_to_close(snapshot, trade)
            if cost_to_close is None:
                return
            if cost_to_close <= trade.target_credit:
                reason = ExitReason.TARGET
            elif cost_to_close >= trade.stop_credit:
                reason = ExitReason.STOP_LOSS

        if reason is None and snapshot.timestamp.time() >= trade.square_off:
            reason = ExitReason.TIME_EXIT

        if reason is None and self._position_strategy is not None:
            override = self._position_strategy.manage_position(context)
            if override is not None and override.is_exit:
                reason = ExitReason.STRATEGY_EXIT

        if reason is not None:
            self._close_position(snapshot, reason)

    def _short_leg_stop_hit(self, snapshot: MarketSnapshot, trade: _OpenTrade) -> bool:
        """Exit if any written option reaches its hard premium stop."""
        for (right, strike), entry_premium in trade.short_entry_premiums.items():
            current = snapshot.option_price(right, strike)
            if current >= entry_premium * trade.short_stop_multiple:
                return True
        return False

    def _directional_exit(
        self, snapshot: MarketSnapshot, trade: _OpenTrade
    ) -> ExitReason | None:
        """Spot-based target/stop for a long-option directional trade."""
        spot = snapshot.spot
        bullish = trade.structure == OptionStructure.LONG_CALL.value
        if bullish:
            if trade.underlying_target is not None and spot >= trade.underlying_target:
                return ExitReason.TARGET
            if trade.underlying_stop is not None and spot <= trade.underlying_stop:
                return ExitReason.STOP_LOSS
        else:
            if trade.underlying_target is not None and spot <= trade.underlying_target:
                return ExitReason.TARGET
            if trade.underlying_stop is not None and spot >= trade.underlying_stop:
                return ExitReason.STOP_LOSS
        return None

    def _close_position(self, snapshot: MarketSnapshot, reason: ExitReason) -> None:
        trade = self._open_trade
        if trade is None:
            return

        lot_size = snapshot.spec.lot_size
        # Close SHORT (written) legs first so the position never becomes more
        # naked during unwind, then close the long hedges.
        ordered = sorted(trade.legs, key=lambda leg: 0 if leg.side == "SELL" else 1)
        exit_commission = 0.0
        for leg in ordered:
            # Calendar legs carry their own lots (ratio); other structures use
            # the single per-structure unit count.
            units = leg.lots * lot_size if trade.kind == "CALENDAR" else trade.units
            qty = units if leg.side == "SELL" else -units
            fill = self.broker.submit(
                Order(
                    symbol=trade.symbol,
                    instrument=leg.instrument,
                    quantity=qty,
                    right=leg.right,
                    strike=leg.strike,
                    expiry_bucket=leg.bucket,
                    tag=f"{trade.strategy_name}_EXIT_{leg.side}",
                ),
                snapshot,
            )
            if fill is None:
                continue
            self._book_fill(fill, leg.right, leg.strike)
            exit_commission += fill.commission

        # Net PnL already includes all costs (booked into realized at fill).
        trade_pnl = self.portfolio.realized_pnl() - trade.realized_start
        total_commission = trade.entry_commission + exit_commission
        entry_value = abs(trade.entry_credit) * trade.units

        self.journal.record_trade(
            TradeRecord(
                strategy=trade.strategy_name,
                symbol=trade.symbol,
                structure=trade.structure,
                entry_time=trade.entry_time,
                exit_time=snapshot.timestamp,
                entry_value=entry_value,
                exit_value=entry_value + trade_pnl,
                pnl=trade_pnl,
                commission=total_commission,
                exit_reason=reason.value,
                lots=trade.lots,
            )
        )
        self.journal.record_event(
            snapshot.timestamp,
            f"EXIT ({reason.value}) {trade.structure} {trade.symbol} "
            f"{trade.body_strike:.0f} pnl Rs {trade_pnl:,.0f}",
        )

        # Allow a fresh entry later in the session by the strategy that opened.
        if self._position_strategy is not None:
            self._position_strategy.reset()
        self._open_trade = None
        self._position_strategy = None

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _mark_portfolio(self, snapshot: MarketSnapshot) -> None:
        """
        Mark every open option leg to a price - chain quote when present, else
        a Black-Scholes fallback. Marking *all* legs (even those whose strike
        drifted out of the chain window) keeps a hedged structure's MTM
        balanced instead of looking spuriously naked.
        """
        trade = self._open_trade
        if trade is not None and trade.kind == "CALENDAR":
            # Price far legs against the next-expiry chain (not the near one).
            for leg in trade.legs:
                pos = self.portfolio.holdings.get(leg.instrument)
                if pos is not None:
                    pos.mark(
                        snapshot.option_price(
                            leg.right, leg.strike, far=leg.bucket == "far"
                        )
                    )
        else:
            for position in self.portfolio.open_positions():
                if position.strike is None or position.right is None:
                    continue
                position.mark(snapshot.option_price(position.right, position.strike))
        self.portfolio.capital.update_high_water_mark(self.portfolio.unrealized_pnl())

    def _book_fill(self, fill, right: OptionRight, strike: float) -> None:
        self.portfolio.apply_fill(
            symbol=fill.symbol,
            instrument=fill.instrument,
            quantity=fill.quantity,
            price=fill.price,
            right=right,
            strike=strike,
            timestamp=fill.timestamp,
        )
        if fill.commission:
            # Reflect costs in equity and per-trade realized PnL.
            self.portfolio.capital.book_realized(-fill.commission)

    def _cost_to_close(
        self, snapshot: MarketSnapshot, trade: _OpenTrade
    ) -> float | None:
        """
        Per-unit net cost to flatten the structure now: pay to buy back the
        shorts, receive from selling the longs. For a naked straddle this is
        just the current body premium; for an Iron Fly it nets the wings.
        Profit when this falls below the entry credit.
        """
        net = 0.0
        for leg in trade.legs:
            price = snapshot.option_price(leg.right, leg.strike)
            net += price if leg.side == "SELL" else -price
        return net

    def _instrument(
        self, symbol: str, strike: float, right: OptionRight, bucket: str = "near"
    ) -> str:
        # Far legs get a suffix so near/far same-strike legs are distinct
        # positions (a calendar can be short near CE and long far CE at the
        # same strike).
        suffix = "_F" if bucket == "far" else ""
        return f"{symbol}{strike:.0f}{right.value[0]}E{suffix}"

    @staticmethod
    def _right(value: object) -> OptionRight:
        token = str(value).upper()
        if token in ("CALL", "CE", "C", "OPTIONRIGHT.CALL"):
            return OptionRight.CALL
        return OptionRight.PUT

    def _build_context(self, snapshot: MarketSnapshot) -> MarketContext:
        ts = snapshot.timestamp
        spec = snapshot.spec
        context = MarketContext(
            symbol=spec.symbol,
            exchange=spec.exchange,
            timeframe=f"{self.config.bar_minutes}m",
            timestamp=ts,
            execution_mode=self.config.execution_mode,
            volatility_regime=self._vol_regime(snapshot.implied_vol),
            close_price=snapshot.spot,
            last_price=snapshot.spot,
            open_price=snapshot.candle.open,
            high_price=snapshot.candle.high,
            low_price=snapshot.candle.low,
            implied_volatility=snapshot.implied_vol,
            vix=snapshot.vix,
            is_market_open=self.session.is_open(ts),
            is_expiry=(snapshot.expiry == ts.date()),
            minutes_from_open=self.session.minutes_from_open(ts),
            minutes_to_close=self.session.minutes_to_close(ts),
        )
        context.metadata["option_chain"] = snapshot.option_chain
        if self.time_window_gate is not None:
            context.metadata["time_window_gate"] = self.time_window_gate
        context.metadata["live_chain"] = any(
            quote.has_market_data for quote in snapshot.option_chain.quotes.values()
        )
        context.metadata["strike_step"] = spec.strike_step
        context.metadata["lot_size"] = spec.lot_size
        if snapshot.far_chain is not None:
            context.metadata["option_chain_far"] = snapshot.far_chain

        # Only candles strictly before this snapshot are completed. Repeated
        # live polls share a timestamp, so their last candle remains forming and
        # is excluded from RV to keep the AUTO decision point-in-time.
        completed_candles = self._recent_candles
        if (
            completed_candles
            and snapshot.candle.timestamp <= completed_candles[-1].timestamp
        ):
            completed_candles = completed_candles[:-1]
        rv = annualized_realized_volatility(
            completed_candles,
            bar_minutes=self.config.bar_minutes,
        )
        if rv is not None:
            context.historical_volatility = rv
        context.metadata["rv_completed_candles"] = min(len(completed_candles), 61)

        # ── Market structure from indicators (drives regime + strategy routing) ──
        if (
            not self._recent_candles
            or snapshot.candle.timestamp > self._recent_candles[-1].timestamp
        ):
            self._recent_candles.append(snapshot.candle)
        else:
            # Dhan polls several times inside one minute; replace the forming
            # bar instead of counting every poll as a separate candle.
            self._recent_candles[-1] = snapshot.candle
        if len(self._recent_candles) > 250:
            self._recent_candles = self._recent_candles[-250:]
        struct = analyse(self._recent_candles, iv=snapshot.implied_vol)
        if struct is not None:
            context.ema_fast = struct.ema_fast
            context.ema_slow = struct.ema_slow
            context.adx = struct.adx
            context.atr = struct.atr
            context.trend = struct.trend
            context.volatility_regime = struct.vol_regime
            context.indicators.update(
                {"rsi": struct.rsi, "adx": struct.adx, "atr": struct.atr}
            )
        return context

    @staticmethod
    def _vol_regime(iv: float) -> VolatilityRegime:
        if iv < 0.10:
            return VolatilityRegime.LOW
        if iv < 0.18:
            return VolatilityRegime.NORMAL
        if iv < 0.30:
            return VolatilityRegime.HIGH
        return VolatilityRegime.EXTREME
