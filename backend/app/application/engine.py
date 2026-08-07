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

from dataclasses import dataclass, field
from datetime import date, datetime, time
from math import log, sqrt

from app.domains.analytics.journal import TradeJournal, TradeRecord
from app.domains.execution.broker import Broker, Order
from app.domains.execution.feed import DataFeed, MarketSnapshot
from app.domains.market.session import NSE_SESSION, TradingSession
from app.domains.portfolio.portfolio import Portfolio
from app.domains.risk.position_sizing import PositionSizer
from app.domains.risk.risk_engine import RiskEngine
from app.domains.shared.enums import (
    ExecutionMode,
    ExitReason,
    OptionRight,
    OptionStructure,
    TrendDirection,
    VolatilityRegime,
)
from app.domains.strategy.contracts.context import MarketContext
from app.domains.strategy.contracts.signal import Signal
from app.domains.strategy.contracts.strategy import BaseStrategy


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


@dataclass(slots=True)
class _OpenTrade:
    """Engine bookkeeping for one open (possibly hedged) option structure."""

    structure: str
    symbol: str
    body_strike: float
    lots: int
    units: int
    entry_time: datetime
    entry_credit: float  # per-unit NET credit collected
    target_credit: float  # per-unit cost-to-close target
    stop_credit: float  # per-unit cost-to-close stop
    square_off: time
    realized_start: float  # portfolio realized PnL captured before entry
    entry_commission: float = 0.0  # transaction costs paid on entry
    legs: list[_Leg] = field(default_factory=list)


class TradingEngine:
    """Bar-driven trade lifecycle orchestrator."""

    def __init__(
        self,
        *,
        strategy: BaseStrategy,
        feed: DataFeed,
        broker: Broker,
        portfolio: Portfolio,
        risk_engine: RiskEngine,
        sizer: PositionSizer | None = None,
        journal: TradeJournal | None = None,
        config: EngineConfig | None = None,
        session: TradingSession = NSE_SESSION,
    ) -> None:
        self.strategy = strategy
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
        self._current_day: date | None = None
        self._recent_closes: list[float] = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def run(self) -> TradeJournal:
        """Run the engine to exhaustion over the feed and return the journal."""
        self.strategy.initialize()
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
        self.strategy.pre_market(context)
        self.risk.start_session(self.portfolio.equity())
        self.journal.record_event(
            snapshot.timestamp, f"Session start (equity {self.portfolio.equity():,.0f})"
        )

    def _end_of_day(self, snapshot: MarketSnapshot) -> None:
        if self._open_trade is not None:
            self._close_position(snapshot, ExitReason.TIME_EXIT)
        context = self._build_context(snapshot)
        self.strategy.post_market(context)
        self.journal.record_equity(snapshot.timestamp, self.portfolio.equity())

    # ------------------------------------------------------------------
    # Per-bar processing
    # ------------------------------------------------------------------
    def _on_bar(self, snapshot: MarketSnapshot) -> None:
        self._update_market_history(snapshot)
        context = self._build_context(snapshot)
        self.portfolio.mark_to_chain(snapshot.option_chain)

        if self.config.record_equity_each_bar:
            self.journal.record_equity(snapshot.timestamp, self.portfolio.equity())

        # Continuous account-level risk monitoring.
        decision = self.risk.update(self.portfolio, snapshot.timestamp)
        if decision.kill_switch_tripped:
            if self._open_trade is not None:
                self._close_position(snapshot, ExitReason.KILL_SWITCH)
            self.journal.record_event(
                snapshot.timestamp, f"KILL SWITCH: {decision.reason}"
            )
            return

        if self._open_trade is None:
            signal = self.strategy.generate_signal(context)
            if signal is not None and signal.is_entry:
                self._open_position(signal, snapshot)
        else:
            self._manage_open_trade(snapshot, context)

    # ------------------------------------------------------------------
    # Position lifecycle
    # ------------------------------------------------------------------
    def _open_position(self, signal: Signal, snapshot: MarketSnapshot) -> None:
        meta = signal.metadata
        leg_specs = meta.get("legs")
        if not isinstance(leg_specs, list) or not leg_specs:
            self.strategy.reset()
            return

        spec = snapshot.spec
        body_strike = float(meta.get("body_strike", 0.0))
        entry_credit = float(meta.get("entry_credit", 0.0))
        wing_width = meta.get("wing_width")  # None when naked

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
        if wing_width is not None:
            max_loss_per_unit = max(float(wing_width) - entry_credit, 1.0)
            margin_per_lot = max_loss_per_unit * spec.lot_size
            allocation = signal.requested_risk or self.config.capital_allocation
        else:
            margin_per_lot = self.sizer.margin_per_lot(
                spot=snapshot.spot, lot_size=spec.lot_size
            )
            allocation = self.config.capital_allocation

        sizing = self.sizer.size_for_margin(
            capital=self.portfolio.capital.starting_capital,
            allocation_fraction=allocation,
            margin_per_lot=margin_per_lot,
            lot_size=spec.lot_size,
        )
        if not sizing.is_tradable:
            self.strategy.reset()
            return

        entry_gate = self.risk.approve_entry(
            self.portfolio, new_capital=sizing.capital_used
        )
        if not entry_gate.approved:
            self.journal.record_event(
                snapshot.timestamp, f"Entry blocked: {entry_gate.reason}"
            )
            self.strategy.reset()
            return

        realized_start = self.portfolio.realized_pnl()

        # HEDGE-FIRST EXECUTION: submit BUY (protective) legs before SELL
        # (written) legs so the broker only blocks the reduced spread margin.
        ordered = sorted(legs, key=lambda leg: 0 if leg.side == "BUY" else 1)
        entry_commission = 0.0
        actual_entry_credit = 0.0
        filled_legs: list[_Leg] = []
        failed_leg = False
        for leg in ordered:
            qty = sizing.units if leg.side == "BUY" else -sizing.units
            fill = self.broker.submit(
                Order(
                    symbol=spec.symbol,
                    instrument=leg.instrument,
                    quantity=qty,
                    right=leg.right,
                    strike=leg.strike,
                    tag=f"TB001_ENTRY_{leg.side}",
                ),
                snapshot,
            )
            if fill is None:
                failed_leg = True
                break
            self._book_fill(fill, leg.right, leg.strike)
            entry_commission += fill.commission
            actual_entry_credit += (
                (-fill.quantity * fill.price) / sizing.units
            )
            filled_legs.append(leg)

        # Multi-leg structures are atomic from the strategy's perspective.
        # If any leg cannot be filled, flatten whatever did fill immediately
        # and do not create a phantom open trade.
        if failed_leg or len(filled_legs) != len(legs):
            for leg in reversed(filled_legs):
                qty = sizing.units if leg.side == "SELL" else -sizing.units
                fill = self.broker.submit(
                    Order(
                        symbol=spec.symbol,
                        instrument=leg.instrument,
                        quantity=qty,
                        right=leg.right,
                        strike=leg.strike,
                        tag="TB001_ENTRY_ROLLBACK",
                    ),
                    snapshot,
                )
                if fill is not None:
                    self._book_fill(fill, leg.right, leg.strike)
            self.strategy.reset()
            self.journal.record_event(
                snapshot.timestamp, "Entry cancelled: incomplete multi-leg fill"
            )
            return

        if actual_entry_credit <= 0.0:
            self.strategy.reset()
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
        )
        self.risk.record_trade()
        self.journal.record_event(
            snapshot.timestamp,
            f"ENTER {self._open_trade.structure} {spec.symbol} "
            f"{body_strike:.0f} x{sizing.lots} credit {actual_entry_credit:.2f}"
            + (f" (margin/lot Rs {margin_per_lot:,.0f})" if wing_width else ""),
        )

    def _manage_open_trade(
        self, snapshot: MarketSnapshot, context: MarketContext
    ) -> None:
        trade = self._open_trade
        assert trade is not None

        cost_to_close = self._cost_to_close(snapshot, trade)
        if cost_to_close is None:
            return

        reason: ExitReason | None = None
        if cost_to_close <= trade.target_credit:
            reason = ExitReason.TARGET
        elif cost_to_close >= trade.stop_credit:
            reason = ExitReason.STOP_LOSS
        elif snapshot.timestamp.time() >= trade.square_off:
            reason = ExitReason.TIME_EXIT
        else:
            override = self.strategy.manage_position(context)
            if override is not None and override.is_exit:
                reason = ExitReason.STRATEGY_EXIT

        if reason is not None:
            self._close_position(snapshot, reason)

    def _close_position(self, snapshot: MarketSnapshot, reason: ExitReason) -> None:
        trade = self._open_trade
        if trade is None:
            return

        # Close SHORT (written) legs first so the position never becomes more
        # naked during unwind, then close the long hedges.
        ordered = sorted(trade.legs, key=lambda leg: 0 if leg.side == "SELL" else 1)
        exit_commission = 0.0
        for leg in ordered:
            # Reverse the entry: buy back shorts, sell longs.
            qty = trade.units if leg.side == "SELL" else -trade.units
            fill = self.broker.submit(
                Order(
                    symbol=trade.symbol,
                    instrument=leg.instrument,
                    quantity=qty,
                    right=leg.right,
                    strike=leg.strike,
                    tag=f"TB001_EXIT_{leg.side}",
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

        self.journal.record_trade(
            TradeRecord(
                strategy=self.strategy.name,
                symbol=trade.symbol,
                structure=trade.structure,
                entry_time=trade.entry_time,
                exit_time=snapshot.timestamp,
                entry_value=trade.entry_credit * trade.units,
                exit_value=trade_pnl + trade.entry_credit * trade.units,
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

        self._open_trade = None
        # Allow a fresh entry later in the session.
        self.strategy.reset()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
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
        chain = snapshot.option_chain
        net = 0.0
        for leg in trade.legs:
            quote = chain.get(leg.strike, leg.right)
            if quote is None:
                return None
            net += quote.price if leg.side == "SELL" else -quote.price
        return net

    def _instrument(self, symbol: str, strike: float, right: OptionRight) -> str:
        return f"{symbol}{strike:.0f}{right.value[0]}E"

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
            historical_volatility=self._historical_volatility(),
            ema_fast=self._ema(8),
            ema_slow=self._ema(21),
            trend=self._trend(),
            adx=self._trend_strength(),
            is_market_open=self.session.is_open(ts),
            is_expiry=(snapshot.expiry == ts.date()),
            minutes_from_open=self.session.minutes_from_open(ts),
            minutes_to_close=self.session.minutes_to_close(ts),
        )
        context.metadata["option_chain"] = snapshot.option_chain
        context.metadata["strike_step"] = spec.strike_step
        return context

    def _update_market_history(self, snapshot: MarketSnapshot) -> None:
        self._recent_closes.append(snapshot.spot)
        if len(self._recent_closes) > 100:
            del self._recent_closes[:-100]

    def _ema(self, period: int) -> float:
        values = self._recent_closes[-period:]
        if not values:
            return 0.0
        alpha = 2.0 / (len(values) + 1.0)
        ema = values[0]
        for value in values[1:]:
            ema = alpha * value + (1.0 - alpha) * ema
        return ema

    def _historical_volatility(self) -> float:
        if len(self._recent_closes) < 6:
            return 0.0
        returns = [
            log(curr / prev)
            for prev, curr in zip(self._recent_closes[-31:-1], self._recent_closes[-30:])
            if prev > 0.0 and curr > 0.0
        ]
        if len(returns) < 5:
            return 0.0
        mean = sum(returns) / len(returns)
        variance = sum((value - mean) ** 2 for value in returns) / len(returns)
        return sqrt(variance * 252 * (375 / max(self.config.bar_minutes, 1)))

    def _trend(self):
        if len(self._recent_closes) < 21:
            return TrendDirection.SIDEWAYS
        fast = self._ema(8)
        slow = self._ema(21)
        spread = (fast - slow) / slow if slow else 0.0
        if spread > 0.0015:
            return TrendDirection.BULLISH
        if spread < -0.0015:
            return TrendDirection.BEARISH
        return TrendDirection.SIDEWAYS

    def _trend_strength(self) -> float:
        if len(self._recent_closes) < 21:
            return 0.0
        fast = self._ema(8)
        slow = self._ema(21)
        recent = self._recent_closes[-14:]
        atr = sum(
            abs(curr - prev) for prev, curr in zip(recent, recent[1:])
        ) / max(len(recent) - 1, 1)
        return min(abs(fast - slow) / atr * 10.0, 100.0) if atr else 0.0

    @staticmethod
    def _vol_regime(iv: float) -> VolatilityRegime:
        if iv < 0.10:
            return VolatilityRegime.LOW
        if iv < 0.18:
            return VolatilityRegime.NORMAL
        if iv < 0.30:
            return VolatilityRegime.HIGH
        return VolatilityRegime.EXTREME
