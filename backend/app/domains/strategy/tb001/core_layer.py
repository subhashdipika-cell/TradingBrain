"""
TradingBrain

TB001 - Dynamic Theta Harvesting
Core Layer
"""

from __future__ import annotations

from datetime import time

from app.domains.market.option_chain import OptionChain
from app.domains.strategy.contracts.context import MarketContext
from app.domains.strategy.contracts.signal import Signal
from app.domains.shared.enums import (
    MarketRegime,
    OptionRight,
    OptionStructure,
    OrderSide,
    PositionSide,
    SignalType,
    VolatilityRegime,
)
from app.domains.strategy.tb001.configuration import TB001Configuration


class CoreLayer:
    """
    Implements the core trading logic for TB001.

    Phase 1
    -------
    - Time-based entry
    - Market validation
    - Basic regime filter
    - Basic volatility filter

    Future Phases
    -------------
    - ATM Strike Selection
    - Dynamic Strike Shift
    - Mean Reversion
    - Tactical Buying
    - Premium Monitoring
    """

    def __init__(self, config: TB001Configuration) -> None:
        self.config = config
        self._position_open = False

    def evaluate(
        self,
        context: MarketContext,
    ) -> Signal | None:
        """
        Evaluate whether a new short-straddle entry should be generated.

        The option chain and instrument spec are supplied by the engine via
        ``context.metadata`` (keys ``option_chain`` and ``strike_step``).
        """

        if not context.is_market_open:
            return None

        if self._position_open:
            return None

        if not self.should_enter(context):
            return None

        chain = context.metadata.get("option_chain")
        if not isinstance(chain, OptionChain):
            return None

        # Pick the strike actually present in the chain nearest to spot. This
        # is robust to real option chains that only quote strikes around ATM.
        strike = chain.nearest_strike(context.last_price or chain.underlying)
        if strike is None:
            return None

        straddle = chain.straddle(strike)
        if straddle is None:
            return None

        call_quote, put_quote = straddle
        body_premium = call_quote.price + put_quote.price

        # Use both an absolute and a notional-scaled floor. This prevents a
        # fixed premium threshold from behaving very differently by symbol.
        minimum_body_premium = max(
            self.config.min_premium,
            context.last_price * self.config.min_body_premium_pct,
        )
        if body_premium < minimum_body_premium:
            return None

        plan = self._build_structure(chain, strike)
        if plan is None:
            return None
        structure, legs, entry_credit, wing_width = plan

        if entry_credit <= 0:
            return None

        # A defined-risk spread can still have poor economics when the wings
        # are too expensive. Reject trades whose best-case credit is too small
        # relative to the maximum spread width.
        if wing_width is not None:
            required_ratio = (
                self.config.expiry_min_credit_to_width
                if context.is_expiry
                else self.config.min_credit_to_width
            )
            if entry_credit / wing_width < required_ratio:
                return None

        self._position_open = True

        expiry_mode = context.is_expiry
        return Signal(
            strategy="TB001",
            symbol=context.symbol,
            signal_type=SignalType.SELL,
            side=OrderSide.SELL,
            position_side=PositionSide.SHORT,
            requested_risk=(
                self.config.expiry_position_risk
                if expiry_mode
                else self.config.max_position_risk
            ),
            confidence=0.80,
            score=entry_credit,
            reason=f"{structure.value} entry @ {strike:.0f}",
            metadata={
                "structure": structure.value,
                "body_strike": strike,
                "legs": legs,
                "entry_credit": entry_credit,
                "wing_width": wing_width,  # None when naked
                "target_profit_pct": self.config.target_profit_pct,
                "stop_loss_pct": (
                    min(self.config.stop_loss_pct, 0.25)
                    if expiry_mode
                    else self.config.stop_loss_pct
                ),
                "square_off_time": (
                    self.config.expiry_square_off_time
                    if expiry_mode
                    else self.config.square_off_time
                ),
                "expiry_mode": expiry_mode,
            },
        )

    def _build_structure(
        self, chain: OptionChain, body: float
    ) -> tuple[OptionStructure, list[dict], float, float | None] | None:
        """
        Build the leg-list for the entry. Returns
        ``(structure, legs, entry_credit, wing_width)`` or ``None``.

        Each leg is ``{"right", "strike", "side"}`` where ``side`` is ``BUY``
        for protective (hedge) legs and ``SELL`` for written legs. Hedges are
        listed first so the engine can submit them before the writes
        (hedge-first execution => reduced margin).
        """
        call = chain.get(body, OptionRight.CALL)
        put = chain.get(body, OptionRight.PUT)
        if call is None or put is None:
            return None
        body_credit = call.price + put.price

        if not self.config.hedge_enabled:
            legs = [
                {"right": "CALL", "strike": body, "side": "SELL"},
                {"right": "PUT", "strike": body, "side": "SELL"},
            ]
            return OptionStructure.SHORT_STRADDLE, legs, body_credit, None

        # Iron Fly: buy OTM wings `hedge_wing_strikes` strikes out, sell ATM.
        complete = [
            s
            for s in chain.strikes()
            if chain.get(s, OptionRight.CALL) and chain.get(s, OptionRight.PUT)
        ]
        if body not in complete:
            return None
        idx = complete.index(body)
        n = self.config.hedge_wing_strikes
        call_idx = idx + n
        put_idx = idx - n
        if call_idx >= len(complete) or put_idx < 0:
            return None  # wings unavailable in chain; skip rather than go naked

        wing_call = complete[call_idx]
        wing_put = complete[put_idx]
        wc = chain.get(wing_call, OptionRight.CALL)
        wp = chain.get(wing_put, OptionRight.PUT)
        if wc is None or wp is None:
            return None

        net_credit = body_credit - (wc.price + wp.price)
        wing_width = max(abs(wing_call - body), abs(body - wing_put))

        legs = [
            {"right": "CALL", "strike": wing_call, "side": "BUY"},  # hedge
            {"right": "PUT", "strike": wing_put, "side": "BUY"},  # hedge
            {"right": "CALL", "strike": body, "side": "SELL"},  # write
            {"right": "PUT", "strike": body, "side": "SELL"},  # write
        ]
        return OptionStructure.IRON_FLY, legs, net_credit, wing_width

    def should_enter(
        self,
        context: MarketContext,
    ) -> bool:
        """
        Phase-1 Entry Rules

        Conditions
        ----------
        1. No existing position.
        2. Entry time reached.
        3. Market regime must be known.
        4. Volatility must not be extreme.
        """

        if self._position_open:
            return False

        current_time = context.timestamp.time()

        entry_time = time.fromisoformat(self.config.entry_time)

        if current_time < entry_time:
            return False

        # Expiry trades are allowed, but use a separate earlier cutoff.
        if context.is_expiry:
            if not self.config.expiry_trading_enabled:
                return False
            if current_time >= time.fromisoformat(self.config.expiry_entry_cutoff):
                return False
        elif current_time >= time.fromisoformat(self.config.no_new_entry_after):
            return False

        if context.market_regime in (MarketRegime.UNKNOWN, MarketRegime.TRENDING):
            return False

        if context.volatility_regime in (
            VolatilityRegime.LOW,
            VolatilityRegime.EXTREME,
        ):
            return False

        # Premium selling needs an IV edge over recent realized volatility.
        # If no realized-vol estimate is available (e.g. an isolated unit
        # test or the first few bars), do not invent one and allow the signal.
        if (
            context.historical_volatility > 0.0
            and context.implied_volatility
            < context.historical_volatility * 1.05
        ):
            return False

        return True

    def should_exit(
        self,
        context: MarketContext,
    ) -> bool:
        """
        Exit logic.

        Placeholder for future implementation.
        """
        return False

    def should_shift_strike(
        self,
        context: MarketContext,
    ) -> bool:
        """
        Dynamic strike adjustment.

        Placeholder for future implementation.
        """
        return False

    def should_add_mean_reversion(
        self,
        context: MarketContext,
    ) -> bool:
        """
        Mean reversion entry.

        Placeholder for future implementation.
        """
        return False

    def reset(self) -> None:
        """
        Reset the strategy for the next trading session.
        """
        self._position_open = False
