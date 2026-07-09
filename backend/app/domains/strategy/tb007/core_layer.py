"""
TradingBrain

TB007 - Convexity Buy
Core Layer

Turns the four Taleb gates into an entry signal:

  1. CHEAP   - implied volatility <= ``max_entry_iv`` (convexity on sale).
  2. CONVEX  - buy a near-ATM long option; premium paid is the capped max loss
               (the engine sizes to it and prices it long gamma + long vega).
  3. COILED  - a live Bollinger squeeze (bandwidth in the bottom 30% of its
               recent range) - real asymmetry, positioned before the expansion.
  4. NO-DECAY- skip 0-DTE (expiry-day) buys; the platform also blocks the
               09:15-10:15 open; exits square off by 15:15.

Two structure modes (config ``neutral_straddle``):

* **directional** (default): buy a long CALL on an up-break of the coil, a long
  PUT on a down-break. Routes through the engine's directional debit path.
  Signal carries NO ``legs``/``straddle_legs`` key.

* **neutral straddle**: on cheap + coiled, buy the ATM straddle (call + put) -
  no directional guess, profits from a large move either way. Routes through
  the engine's ``LONG_VOL`` path via ``metadata["straddle_legs"]``.
"""

from __future__ import annotations

from datetime import time

from app.domains.shared.enums import (
    OrderSide,
    PositionSide,
    SignalType,
)
from app.domains.strategy.contracts.context import MarketContext
from app.domains.strategy.contracts.signal import Signal
from app.domains.strategy.tb007.configuration import TB007Configuration


class CoreLayer:
    """Core entry logic for TB007 (Convexity Buy)."""

    def __init__(self, config: TB007Configuration) -> None:
        self.config = config
        self._position_open = False
        # Countdown of bars since the last live squeeze (grace window for the
        # breakout to occur after the coil). Refreshed while a squeeze is on.
        self._squeeze_countdown = 0

    # ------------------------------------------------------------------
    def evaluate(self, context: MarketContext) -> Signal | None:
        if not context.is_market_open or self._position_open:
            return None

        ind = context.indicators

        # Track the squeeze grace window every evaluated bar.
        if bool(ind.get("squeeze")):
            self._squeeze_countdown = self.config.squeeze_grace_bars + 1
        elif self._squeeze_countdown > 0:
            self._squeeze_countdown -= 1

        # ---- Common gates -------------------------------------------------
        if not self._within_entry_window(context):
            return None
        # Gate 4 - NOT PAYING DECAY: no 0-DTE (expiry-day) buys.
        if self.config.block_expiry_day and context.is_expiry:
            return None
        # Gate 1 - CHEAP: implied vol must be low (convexity on sale).
        iv = context.implied_volatility
        if iv <= 0.0 or iv > self.config.max_entry_iv:
            return None
        # Gate 3 - COILED: a squeeze must be live (now or within grace bars).
        if self._squeeze_countdown <= 0:
            return None

        if self.config.neutral_straddle:
            return self._straddle_signal(context, iv)
        return self._directional_signal(context, iv)

    # ------------------------------------------------------------------
    def _directional_signal(self, context: MarketContext, iv: float) -> Signal | None:
        """Long CALL on an up-break of the coil, long PUT on a down-break."""
        ind = context.indicators
        upper = ind.get("bb_upper")
        lower = ind.get("bb_lower")
        mid = ind.get("bb_mid")
        if upper is None or lower is None or mid is None or mid <= 0:
            return None

        price = context.last_price or context.close_price
        if price <= 0:
            return None

        if price > upper:
            side, position_side, order_side = (
                SignalType.BUY,
                PositionSide.LONG,
                OrderSide.BUY,
            )
            stop_spot = float(mid)
            risk = price - stop_spot
            if risk <= 0:
                return None
            target_spot = price + self.config.target_r * risk
            structure = "LONG_CALL"
        elif price < lower:
            side, position_side, order_side = (
                SignalType.SELL,
                PositionSide.SHORT,
                OrderSide.SELL,
            )
            stop_spot = float(mid)
            risk = stop_spot - price
            if risk <= 0:
                return None
            target_spot = price - self.config.target_r * risk
            structure = "LONG_PUT"
        else:
            return None  # coiled but not yet breaking - wait

        self._position_open = True
        return Signal(
            strategy=self.config.strategy_id,
            symbol=context.symbol,
            signal_type=side,
            side=order_side,
            position_side=position_side,
            entry_price=price,
            stop_loss=stop_spot,
            take_profit=target_spot,
            requested_risk=self.config.requested_risk,
            confidence=self.config.default_confidence,
            score=float(ind.get("bb_bandwidth", 0.0)),
            reason=(
                f"Convexity buy {structure}: squeeze break @ {price:.0f} "
                f"(IV {iv * 100:.1f}%, stop {stop_spot:.0f}, tgt {target_spot:.0f})"
            ),
            tags=["TB007", "convexity", "long-vol", structure.lower()],
            metadata={
                "iv": iv,
                "bb_bandwidth": ind.get("bb_bandwidth"),
                "squeeze_grace": self._squeeze_countdown,
                "target_r": self.config.target_r,
            },
        )

    # ------------------------------------------------------------------
    def _straddle_signal(self, context: MarketContext, iv: float) -> Signal | None:
        """Delta-neutral long straddle on cheap + coiled - no directional guess."""
        chain = context.metadata.get("option_chain")
        if chain is None:
            return None
        price = context.last_price or context.close_price
        strike = chain.nearest_strike(price if price > 0 else None)
        if strike is None:
            return None

        self._position_open = True
        return Signal(
            strategy=self.config.strategy_id,
            symbol=context.symbol,
            signal_type=SignalType.BUY,
            side=OrderSide.BUY,
            position_side=PositionSide.LONG,  # long volatility
            entry_price=price,
            requested_risk=self.config.requested_risk,
            confidence=self.config.default_confidence,
            score=float(context.indicators.get("bb_bandwidth", 0.0)),
            reason=(
                f"Convexity buy LONG_STRADDLE: cheap + coiled @ {strike:.0f} "
                f"(IV {iv * 100:.1f}%)"
            ),
            tags=["TB007", "convexity", "long-vol", "long_straddle"],
            metadata={
                "straddle_legs": [
                    {"right": "CALL", "strike": strike, "side": "BUY"},
                    {"right": "PUT", "strike": strike, "side": "BUY"},
                ],
                "body_strike": strike,
                "structure": "LONG_STRADDLE",
                "target_profit_pct": self.config.straddle_target_pct,
                "stop_loss_pct": self.config.straddle_stop_pct,
                "hold_overnight": self.config.hold_overnight,
                "max_hold_sessions": self.config.max_hold_sessions,
                "iv": iv,
            },
        )

    # ------------------------------------------------------------------
    def _within_entry_window(self, context: MarketContext) -> bool:
        current = context.timestamp.time()
        if current < time.fromisoformat(self.config.entry_time):
            return False
        if current >= time.fromisoformat(self.config.no_new_entry_after):
            return False
        return True

    def reset(self) -> None:
        self._position_open = False
        self._squeeze_countdown = 0
