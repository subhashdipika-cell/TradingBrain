"""
TradingBrain

TB002 - ICT Liquidity Sweep Inversion Core Layer
"""

from __future__ import annotations

from app.domains.shared.enums import (
    MarketRegime,
    OrderSide,
    PositionSide,
    SignalType,
    VolatilityRegime,
)
from app.domains.strategy.contracts.context import MarketContext
from app.domains.strategy.contracts.signal import Signal
from app.domains.strategy.tb002.configuration import TB002Configuration
from app.domains.strategy.tb002.exceptions import InvalidSetupError
from app.domains.strategy.tb002.models import (
    ICTDirection,
    ICTSetup,
    normalise_timeframe,
)


class CoreLayer:
    """
    Implements the TB002 entry model.

    TB002 is intentionally metadata-driven because the shared
    ``MarketContext`` does not include raw multi-timeframe candles. Upstream
    detectors can provide the model layers in ``context.metadata["tb002_setup"]``.
    """

    def __init__(self, config: TB002Configuration) -> None:
        self.config = config
        self._position_open = False
        self._current_direction: ICTDirection | None = None

    def evaluate(self, context: MarketContext) -> Signal | None:
        if self._position_open:
            return None

        if not self.should_enter(context):
            return None

        try:
            setup = ICTSetup.from_metadata(
                context.metadata.get("tb002_setup"),
                default_entry_price=context.last_price or context.close_price or None,
            )
        except InvalidSetupError:
            return None

        if setup is None:
            return None

        if not self._valid_setup(setup, context):
            return None

        confidence = self._confidence(setup, context)
        if confidence < self.config.min_confidence:
            return None

        risk_reward = setup.risk_reward()
        if risk_reward < self.config.min_risk_reward:
            return None

        requested_risk = self._requested_risk(context)
        signal = self._signal(context, setup, confidence, risk_reward, requested_risk)
        self._position_open = True
        self._current_direction = setup.direction
        return signal

    def should_enter(self, context: MarketContext) -> bool:
        if self.config.require_session_open and not context.is_market_open:
            return False

        current_time = context.timestamp.time()
        if current_time < self.config.entry_start_obj:
            return False

        if current_time >= self.config.no_new_entry_after_obj:
            return False

        if (
            context.volatility_regime == VolatilityRegime.EXTREME
            and not self.config.allow_extreme_volatility
        ):
            return False

        return True

    def manage_position(self, context: MarketContext) -> Signal | None:
        if not self._position_open or self._current_direction is None:
            return None

        position = context.metadata.get("tb002_position")
        if not isinstance(position, dict):
            return None

        should_exit = any(
            bool(position.get(key))
            for key in (
                "should_exit",
                "opposite_inversion",
                "structure_invalidated",
                "stop_to_breakeven_failed",
            )
        )
        if not should_exit:
            return None

        side = (
            OrderSide.SELL
            if self._current_direction is ICTDirection.BULLISH
            else OrderSide.BUY
        )
        reason = str(position.get("reason", "TB002 structure invalidated"))
        return Signal(
            strategy="TB002",
            symbol=context.symbol,
            signal_type=SignalType.EXIT,
            side=side,
            position_side=PositionSide.FLAT,
            reason=reason,
            tags=["TB002", "EXIT"],
            metadata={"exit_context": position},
        )

    def reset(self) -> None:
        self._position_open = False
        self._current_direction = None

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------
    def _valid_setup(self, setup: ICTSetup, context: MarketContext) -> bool:
        if setup.sweep.side is not setup.expected_sweep_side:
            return False

        if not setup.sweep.confirmed:
            return False

        if setup.htf_inversion.direction is not setup.direction:
            return False

        if not setup.htf_inversion.inverted:
            return False

        if setup.htf_inversion.candles_to_invert is not None:
            if (
                setup.htf_inversion.candles_to_invert
                > self.config.max_htf_inversion_candles
            ):
                return False

        if setup.pullback_gap.direction is not setup.direction:
            return False

        if not setup.pullback_gap.tapped:
            return False

        if not self._timeframe_allowed(
            setup.pullback_gap.timeframe, self.config.pullback_timeframes
        ):
            return False

        if setup.trigger.direction is not setup.direction:
            return False

        if not setup.trigger.confirmed:
            return False

        if not self._timeframe_allowed(
            setup.trigger.timeframe, self.config.trigger_timeframes
        ):
            return False

        if setup.setup_time is not None:
            age = context.timestamp - setup.setup_time
            if age.total_seconds() > self.config.max_setup_age_minutes * 60:
                return False

        return self._valid_price_geometry(setup)

    def _valid_price_geometry(self, setup: ICTSetup) -> bool:
        targets = [setup.initial_target, setup.external_target]
        if setup.runner_target is not None:
            targets.append(setup.runner_target)

        if setup.direction is ICTDirection.BEARISH:
            if setup.stop_loss <= setup.entry_price:
                return False
            return all(target < setup.entry_price for target in targets)

        if setup.stop_loss >= setup.entry_price:
            return False
        return all(target > setup.entry_price for target in targets)

    def _timeframe_allowed(self, value: str, allowed: tuple[str, ...]) -> bool:
        normalised = normalise_timeframe(value)
        return normalised in {normalise_timeframe(item) for item in allowed}

    # ------------------------------------------------------------------
    # Scoring and signal construction
    # ------------------------------------------------------------------
    def _confidence(self, setup: ICTSetup, context: MarketContext) -> float:
        confidence = 0.40
        confidence += 0.10 if setup.sweep.confirmed else 0.0
        confidence += 0.15 if setup.htf_inversion.inverted else 0.0
        confidence += 0.10 if setup.pullback_gap.tapped else 0.0
        confidence += 0.10 if setup.pullback_gap.inside_parent else 0.0
        confidence += 0.15 if setup.trigger.confirmed else 0.0

        if setup.htf_inversion.candles_to_invert is not None:
            if (
                setup.htf_inversion.candles_to_invert
                <= self.config.max_htf_inversion_candles
            ):
                confidence += 0.05

        if setup.risk_reward() >= 2.0:
            confidence += 0.05

        if context.market_regime in {
            MarketRegime.REVERSAL,
            MarketRegime.BREAKOUT,
            MarketRegime.TRENDING,
            MarketRegime.VOLATILE,
        }:
            confidence += 0.05

        return min(confidence, 0.95)

    def _requested_risk(self, context: MarketContext) -> float:
        if context.volatility_regime == VolatilityRegime.HIGH:
            return min(
                self.config.high_vol_requested_risk,
                self.config.max_position_risk,
            )
        return min(self.config.default_requested_risk, self.config.max_position_risk)

    def _signal(
        self,
        context: MarketContext,
        setup: ICTSetup,
        confidence: float,
        risk_reward: float,
        requested_risk: float,
    ) -> Signal:
        if setup.direction is ICTDirection.BEARISH:
            signal_type = SignalType.SELL
            order_side = OrderSide.SELL
            position_side = PositionSide.SHORT
        else:
            signal_type = SignalType.BUY
            order_side = OrderSide.BUY
            position_side = PositionSide.LONG

        return Signal(
            strategy="TB002",
            symbol=context.symbol,
            signal_type=signal_type,
            side=order_side,
            position_side=position_side,
            entry_price=setup.entry_price,
            stop_loss=setup.stop_loss,
            take_profit=setup.initial_target,
            requested_risk=requested_risk,
            confidence=confidence,
            score=risk_reward,
            reason=(
                f"{setup.direction.value.title()} liquidity sweep, HTF IFVG, "
                "15m pullback, LTF inversion trigger"
            ),
            tags=[
                "TB002",
                "ICT",
                "LIQUIDITY_SWEEP",
                "IFVG",
                setup.direction.value,
            ],
            metadata={
                "sweep_side": setup.sweep.side.value,
                "sweep_timeframe": setup.sweep.timeframe,
                "htf_inversion_timeframe": setup.htf_inversion.timeframe,
                "pullback_timeframe": setup.pullback_gap.timeframe,
                "trigger_timeframe": setup.trigger.timeframe,
                "risk_points": setup.risk_points(),
                "reward_points": setup.reward_points(),
                "risk_reward": risk_reward,
                "external_target": setup.external_target,
                "runner_target": setup.runner_target,
                "first_trim_fraction": self.config.first_trim_fraction,
                "management_plan": {
                    "first_trim": "trim half at initial target",
                    "stop_after_first_trim": "move remainder to breakeven",
                    "runner_target": setup.runner_target or setup.external_target,
                },
                "notes": list(setup.notes),
            },
        )
