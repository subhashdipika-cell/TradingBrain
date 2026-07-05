"""
TradingBrain

TB002 - Strategy Configuration
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import time

from app.domains.strategy.tb002 import constants
from app.domains.strategy.tb002.exceptions import StrategyConfigurationError


@dataclass(slots=True)
class TB002Configuration:
    """
    Configuration for TB002.

    Multi-timeframe ICT structures are supplied through
    ``MarketContext.metadata["tb002_setup"]`` by the data/intelligence layer.
    """

    strategy_id: str = constants.STRATEGY_ID
    strategy_name: str = constants.STRATEGY_NAME
    strategy_version: str = constants.STRATEGY_VERSION

    market_open: str = constants.MARKET_OPEN.isoformat()
    market_close: str = constants.MARKET_CLOSE.isoformat()
    entry_start: str = constants.DEFAULT_ENTRY_START.isoformat()
    no_new_entry_after: str = constants.NO_NEW_ENTRY_AFTER.isoformat()

    max_strategy_drawdown: float = constants.MAX_STRATEGY_DRAWDOWN
    max_daily_loss: float = constants.MAX_DAILY_LOSS
    max_position_risk: float = constants.MAX_POSITION_RISK
    default_requested_risk: float = constants.DEFAULT_REQUESTED_RISK
    high_vol_requested_risk: float = constants.HIGH_VOL_REQUESTED_RISK

    min_risk_reward: float = constants.MIN_RISK_REWARD
    min_confidence: float = constants.MIN_CONFIDENCE
    max_setup_age_minutes: int = constants.MAX_SETUP_AGE_MINUTES
    max_htf_inversion_candles: int = constants.MAX_HTF_INVERSION_CANDLES
    pullback_timeframes: tuple[str, ...] = constants.PULLBACK_TIMEFRAMES
    trigger_timeframes: tuple[str, ...] = constants.TRIGGER_TIMEFRAMES
    first_trim_fraction: float = constants.FIRST_TRIM_FRACTION

    require_session_open: bool = True
    allow_extreme_volatility: bool = False

    def __post_init__(self) -> None:
        self.validate()

    @property
    def market_open_obj(self) -> time:
        return time.fromisoformat(self.market_open)

    @property
    def market_close_obj(self) -> time:
        return time.fromisoformat(self.market_close)

    @property
    def entry_start_obj(self) -> time:
        return time.fromisoformat(self.entry_start)

    @property
    def no_new_entry_after_obj(self) -> time:
        return time.fromisoformat(self.no_new_entry_after)

    def validate(self) -> None:
        self._validate_times()
        self._validate_fractions()
        self._validate_parameters()

    def _validate_times(self) -> None:
        fields = {
            "market_open": self.market_open,
            "market_close": self.market_close,
            "entry_start": self.entry_start,
            "no_new_entry_after": self.no_new_entry_after,
        }

        parsed: dict[str, time] = {}
        for name, value in fields.items():
            try:
                parsed[name] = time.fromisoformat(value)
            except (TypeError, ValueError) as exc:
                raise StrategyConfigurationError(
                    f"Invalid time for '{name}': {value!r}"
                ) from exc

        if parsed["market_open"] >= parsed["market_close"]:
            raise StrategyConfigurationError(
                "market_open must be earlier than market_close."
            )

        if not (
            parsed["market_open"] <= parsed["entry_start"] <= parsed["market_close"]
        ):
            raise StrategyConfigurationError(
                "entry_start must fall within market hours."
            )

        if not (
            parsed["entry_start"]
            <= parsed["no_new_entry_after"]
            <= parsed["market_close"]
        ):
            raise StrategyConfigurationError(
                "no_new_entry_after must be between entry_start and market_close."
            )

    def _validate_fractions(self) -> None:
        fractions = {
            "max_strategy_drawdown": self.max_strategy_drawdown,
            "max_daily_loss": self.max_daily_loss,
            "max_position_risk": self.max_position_risk,
            "default_requested_risk": self.default_requested_risk,
            "high_vol_requested_risk": self.high_vol_requested_risk,
            "min_confidence": self.min_confidence,
            "first_trim_fraction": self.first_trim_fraction,
        }

        for name, value in fractions.items():
            if not 0.0 <= value <= 1.0:
                raise StrategyConfigurationError(
                    f"'{name}' must be between 0.0 and 1.0, got {value!r}."
                )

    def _validate_parameters(self) -> None:
        if self.min_risk_reward <= 0.0:
            raise StrategyConfigurationError("min_risk_reward must be positive.")

        if self.max_setup_age_minutes <= 0:
            raise StrategyConfigurationError("max_setup_age_minutes must be positive.")

        if self.max_htf_inversion_candles <= 0:
            raise StrategyConfigurationError(
                "max_htf_inversion_candles must be positive."
            )

        if not self.pullback_timeframes:
            raise StrategyConfigurationError("pullback_timeframes cannot be empty.")

        if not self.trigger_timeframes:
            raise StrategyConfigurationError("trigger_timeframes cannot be empty.")
