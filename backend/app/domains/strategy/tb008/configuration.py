"""
TradingBrain

TB008 - Adaptive Calendar Spread Engine - Configuration
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import time

from app.domains.strategy.tb008 import constants
from app.domains.strategy.tb008.exceptions import StrategyConfigurationError


@dataclass(slots=True)
class TB008Configuration:
    """
    Tunable parameters for the Adaptive Calendar Spread Engine.

    Defaults follow the source method (low-VIX, ~2-delta near strangle hedged
    with a next-expiry ratio calendar, exit at ~1% weekly). TradingBrain can
    derive the range / delta / hedge ratio from live data (see the strategy's
    ``derive_from_data`` hook).
    """

    strategy_id: str = constants.STRATEGY_ID
    strategy_name: str = constants.STRATEGY_NAME
    strategy_version: str = constants.STRATEGY_VERSION

    # Session
    entry_time: str = constants.DEFAULT_ENTRY_TIME.isoformat()
    no_new_entry_after: str = constants.NO_NEW_ENTRY_AFTER.isoformat()

    # Volatility gating (India VIX points)
    vix_low_max: float = constants.VIX_LOW_MAX
    vix_medium_max: float = constants.VIX_MEDIUM_MAX
    vix_expansion_risk: float = constants.VIX_EXPANSION_RISK

    # Structure
    target_sell_delta: float = constants.TARGET_SELL_DELTA
    sell_lots: int = constants.SELL_LOTS
    hedge_legs: tuple[tuple[float, int], ...] = constants.HEDGE_LEGS
    weekly_range_pct: float = constants.DEFAULT_WEEKLY_RANGE_PCT

    # Profit / risk
    weekly_profit_target_pct: float = constants.WEEKLY_PROFIT_TARGET_PCT
    max_margin_utilisation: float = constants.MAX_MARGIN_UTILISATION
    max_loss_pct: float = constants.MAX_LOSS_PCT
    max_mtm_swing_pct: float = constants.MAX_MTM_SWING_PCT

    # Behaviour
    derive_from_data: bool = True  # auto-derive range/delta/hedge from IV etc.

    def __post_init__(self) -> None:
        self.validate()

    @property
    def entry_time_obj(self) -> time:
        return time.fromisoformat(self.entry_time)

    @property
    def no_new_entry_after_obj(self) -> time:
        return time.fromisoformat(self.no_new_entry_after)

    def validate(self) -> None:
        for name, value in (
            ("target_sell_delta", self.target_sell_delta),
            ("weekly_range_pct", self.weekly_range_pct),
            ("weekly_profit_target_pct", self.weekly_profit_target_pct),
            ("max_margin_utilisation", self.max_margin_utilisation),
            ("max_loss_pct", self.max_loss_pct),
            ("max_mtm_swing_pct", self.max_mtm_swing_pct),
        ):
            if not 0.0 < value <= 1.0:
                raise StrategyConfigurationError(
                    f"'{name}' must be within (0, 1], got {value!r}."
                )
        if self.sell_lots <= 0:
            raise StrategyConfigurationError("sell_lots must be positive.")
        if not self.hedge_legs:
            raise StrategyConfigurationError("hedge_legs cannot be empty.")
        if not (
            self.vix_low_max < self.vix_medium_max
            and self.vix_expansion_risk <= self.vix_low_max
        ):
            raise StrategyConfigurationError(
                "VIX thresholds must satisfy expansion_risk <= low_max < medium_max."
            )
        for delta, lots in self.hedge_legs:
            if not 0.0 < delta < 1.0 or lots <= 0:
                raise StrategyConfigurationError(
                    f"Invalid hedge leg (delta={delta}, lots={lots})."
                )
