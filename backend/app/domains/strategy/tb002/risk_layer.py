"""
TradingBrain

TB002 - Risk Layer
"""

from __future__ import annotations

from app.domains.shared.enums import VolatilityRegime
from app.domains.strategy.contracts.context import MarketContext
from app.domains.strategy.contracts.signal import Signal
from app.domains.strategy.tb002.configuration import TB002Configuration


class RiskLayer:
    """
    Strategy-specific risk validation for TB002.

    The global risk engine still owns sizing and account-level controls. This
    layer rejects malformed directional signals before they leave the strategy.
    """

    def __init__(self, config: TB002Configuration) -> None:
        self.config = config

    def validate(self, context: MarketContext, signal: Signal | None) -> Signal | None:
        if signal is None:
            return None

        if (
            context.volatility_regime == VolatilityRegime.EXTREME
            and not self.config.allow_extreme_volatility
        ):
            return None

        if signal.entry_price is None:
            return None

        if signal.stop_loss is None:
            return None

        if signal.take_profit is None:
            return None

        risk = abs(signal.entry_price - signal.stop_loss)
        reward = abs(signal.take_profit - signal.entry_price)
        if risk <= 0.0:
            return None

        if reward / risk < self.config.min_risk_reward:
            return None

        signal.requested_risk = min(
            signal.requested_risk,
            self.config.max_position_risk,
        )
        return signal

    def should_activate_kill_switch(self, context: MarketContext) -> bool:
        """Reserved for strategy-level emergency stop logic."""
        return False
