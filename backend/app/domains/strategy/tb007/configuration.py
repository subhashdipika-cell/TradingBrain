"""
TradingBrain

TB007 - Strategy Configuration

Every tunable parameter for the Convexity Buy strategy, defaulted from
:mod:`app.domains.strategy.tb007.constants`. Validated on construction.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import time

from app.domains.strategy.tb007 import constants


class StrategyConfigurationError(ValueError):
    """Raised when a TB007 configuration value is invalid."""


@dataclass(slots=True)
class TB007Configuration:
    """Immutable-by-convention configuration for TB007 (Convexity Buy)."""

    # Identity
    strategy_id: str = constants.STRATEGY_ID
    strategy_name: str = constants.STRATEGY_NAME
    strategy_version: str = constants.STRATEGY_VERSION

    # Session timings (ISO HH:MM:SS strings)
    entry_time: str = constants.DEFAULT_ENTRY_TIME.isoformat()
    no_new_entry_after: str = constants.NO_NEW_ENTRY_AFTER.isoformat()

    # Gates
    max_entry_iv: float = constants.DEFAULT_MAX_ENTRY_IV
    squeeze_grace_bars: int = constants.DEFAULT_SQUEEZE_GRACE_BARS
    block_expiry_day: bool = constants.DEFAULT_BLOCK_EXPIRY_DAY

    # Structure / exits
    target_r: float = constants.DEFAULT_TARGET_R

    # Delta-neutral long-straddle mode (vs directional squeeze-break)
    neutral_straddle: bool = constants.DEFAULT_NEUTRAL_STRADDLE
    straddle_target_pct: float = constants.DEFAULT_STRADDLE_TARGET_PCT
    straddle_stop_pct: float = constants.DEFAULT_STRADDLE_STOP_PCT

    # Overnight holding (straddle mode)
    hold_overnight: bool = constants.DEFAULT_HOLD_OVERNIGHT
    max_hold_sessions: int = constants.DEFAULT_MAX_HOLD_SESSIONS

    # Risk
    requested_risk: float = constants.DEFAULT_REQUESTED_RISK
    max_strategy_drawdown: float = constants.MAX_STRATEGY_DRAWDOWN
    max_daily_loss: float = constants.MAX_DAILY_LOSS
    capital_allocation: float = constants.DEFAULT_INITIAL_CAPITAL
    default_confidence: float = constants.DEFAULT_CONFIDENCE

    def __post_init__(self) -> None:
        self.validate()

    # ------------------------------------------------------------------
    def validate(self) -> None:
        for name in ("entry_time", "no_new_entry_after"):
            value = getattr(self, name)
            try:
                time.fromisoformat(value)
            except (TypeError, ValueError) as exc:
                raise StrategyConfigurationError(
                    f"Invalid time for '{name}': {value!r}"
                ) from exc

        fractions = {
            "max_entry_iv": self.max_entry_iv,
            "requested_risk": self.requested_risk,
            "max_strategy_drawdown": self.max_strategy_drawdown,
            "max_daily_loss": self.max_daily_loss,
            "capital_allocation": self.capital_allocation,
            "default_confidence": self.default_confidence,
            "straddle_target_pct": self.straddle_target_pct,
            "straddle_stop_pct": self.straddle_stop_pct,
        }
        for name, value in fractions.items():
            if not 0.0 < value <= 1.0:
                raise StrategyConfigurationError(
                    f"'{name}' must be in (0.0, 1.0], got {value!r}."
                )

        if self.target_r <= 0.0:
            raise StrategyConfigurationError("target_r must be positive.")
        if self.squeeze_grace_bars < 0:
            raise StrategyConfigurationError("squeeze_grace_bars must be >= 0.")
        if self.max_hold_sessions < 0:
            raise StrategyConfigurationError("max_hold_sessions must be >= 0.")

    # ------------------------------------------------------------------
    @property
    def entry_time_obj(self) -> time:
        return time.fromisoformat(self.entry_time)

    @property
    def no_new_entry_after_obj(self) -> time:
        return time.fromisoformat(self.no_new_entry_after)
