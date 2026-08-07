"""
TradingBrain

TB001 - Strategy Configuration

Centralizes every tunable parameter for the Dynamic Theta Harvesting
strategy. Defaults are sourced from :mod:`app.domains.strategy.tb001.constants`
so there is a single source of truth, while still allowing callers to
override individual values when instantiating the strategy.

All time fields are stored as ISO ``HH:MM:SS`` strings. This keeps the
configuration trivially serializable (JSON / env / DB) while remaining
parseable via :func:`datetime.time.fromisoformat`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import time

from app.domains.strategy.tb001 import constants
from app.domains.strategy.tb001.exceptions import StrategyConfigurationError


@dataclass(slots=True)
class TB001Configuration:
    """
    Immutable-by-convention configuration for TB001.

    Notes
    -----
    Validation runs automatically on construction (``__post_init__``)
    and can be re-run explicitly via :meth:`validate`.
    """

    # ------------------------------------------------------------------
    # Identity
    # ------------------------------------------------------------------
    strategy_id: str = constants.STRATEGY_ID
    strategy_name: str = constants.STRATEGY_NAME
    strategy_version: str = constants.STRATEGY_VERSION

    # ------------------------------------------------------------------
    # Session timings (ISO HH:MM:SS strings)
    # ------------------------------------------------------------------
    market_open: str = constants.MARKET_OPEN.isoformat()
    market_close: str = constants.MARKET_CLOSE.isoformat()
    entry_time: str = constants.DEFAULT_ENTRY_TIME.isoformat()
    no_new_entry_after: str = constants.NO_NEW_ENTRY_AFTER.isoformat()

    # ------------------------------------------------------------------
    # Risk limits (fractions of capital, 0.0 - 1.0)
    # ------------------------------------------------------------------
    max_strategy_drawdown: float = constants.MAX_STRATEGY_DRAWDOWN
    max_daily_loss: float = constants.MAX_DAILY_LOSS
    max_position_risk: float = constants.MAX_POSITION_RISK

    # ------------------------------------------------------------------
    # Strategy parameters
    # ------------------------------------------------------------------
    shift_multiplier: float = constants.DEFAULT_SHIFT_MULTIPLIER
    min_premium: float = constants.DEFAULT_MIN_PREMIUM
    min_body_premium_pct: float = constants.MIN_BODY_PREMIUM_PCT
    min_credit_to_width: float = constants.MIN_CREDIT_TO_WIDTH
    expiry_trading_enabled: bool = True
    expiry_min_credit_to_width: float = constants.EXPIRY_MIN_CREDIT_TO_WIDTH
    expiry_entry_cutoff: str = constants.EXPIRY_ENTRY_CUTOFF.isoformat()
    expiry_square_off_time: str = constants.EXPIRY_SQUARE_OFF.isoformat()
    expiry_position_risk: float = constants.EXPIRY_POSITION_RISK
    capital_allocation: float = constants.DEFAULT_INITIAL_CAPITAL

    # Hedging: trade a defined-risk Iron Fly (short ATM straddle + long OTM
    # wings) instead of a naked short straddle. The hedge dramatically cuts
    # margin and caps the maximum loss.
    hedge_enabled: bool = True
    hedge_wing_strikes: int = 4  # wing distance from ATM, in strike steps

    # Exit rules (fractions of the entry net credit)
    target_profit_pct: float = 0.30  # buy back when credit decays 30%
    stop_loss_pct: float = 0.30  # exit when cost to close expands 30%
    square_off_time: str = "15:15:00"  # force-close before the close

    # ------------------------------------------------------------------
    # Signal defaults
    # ------------------------------------------------------------------
    default_confidence: float = constants.DEFAULT_CONFIDENCE
    default_score: float = constants.DEFAULT_SCORE
    default_requested_risk: float = constants.DEFAULT_REQUESTED_RISK

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def __post_init__(self) -> None:
        self.validate()

    def validate(self) -> None:
        """
        Validate the configuration.

        Raises
        ------
        StrategyConfigurationError
            If any value is out of its allowed range or a time string
            cannot be parsed.
        """
        self._validate_times()
        self._validate_fractions()
        self._validate_parameters()

    # ------------------------------------------------------------------
    # Typed accessors
    # ------------------------------------------------------------------
    @property
    def entry_time_obj(self) -> time:
        """Return :attr:`entry_time` as a :class:`datetime.time`."""
        return time.fromisoformat(self.entry_time)

    @property
    def no_new_entry_after_obj(self) -> time:
        """Return :attr:`no_new_entry_after` as a :class:`datetime.time`."""
        return time.fromisoformat(self.no_new_entry_after)

    @property
    def market_open_obj(self) -> time:
        """Return :attr:`market_open` as a :class:`datetime.time`."""
        return time.fromisoformat(self.market_open)

    @property
    def market_close_obj(self) -> time:
        """Return :attr:`market_close` as a :class:`datetime.time`."""
        return time.fromisoformat(self.market_close)

    # ------------------------------------------------------------------
    # Internal validation helpers
    # ------------------------------------------------------------------
    def _validate_times(self) -> None:
        fields = {
            "market_open": self.market_open,
            "market_close": self.market_close,
            "entry_time": self.entry_time,
            "no_new_entry_after": self.no_new_entry_after,
            "square_off_time": self.square_off_time,
            "expiry_entry_cutoff": self.expiry_entry_cutoff,
            "expiry_square_off_time": self.expiry_square_off_time,
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
            parsed["market_open"] <= parsed["entry_time"] <= parsed["market_close"]
        ):
            raise StrategyConfigurationError(
                "entry_time must fall within market hours."
            )

        if not (
            parsed["entry_time"]
            <= parsed["no_new_entry_after"]
            <= parsed["market_close"]
        ):
            raise StrategyConfigurationError(
                "no_new_entry_after must be between entry_time and " "market_close."
            )

        if parsed["expiry_entry_cutoff"] > parsed["expiry_square_off_time"]:
            raise StrategyConfigurationError(
                "expiry_entry_cutoff must be before expiry_square_off_time."
            )

    def _validate_fractions(self) -> None:
        fractions = {
            "max_strategy_drawdown": self.max_strategy_drawdown,
            "max_daily_loss": self.max_daily_loss,
            "max_position_risk": self.max_position_risk,
            "capital_allocation": self.capital_allocation,
            "default_requested_risk": self.default_requested_risk,
            "default_confidence": self.default_confidence,
            "default_score": self.default_score,
            "target_profit_pct": self.target_profit_pct,
            "stop_loss_pct": self.stop_loss_pct,
            "min_body_premium_pct": self.min_body_premium_pct,
            "min_credit_to_width": self.min_credit_to_width,
            "expiry_min_credit_to_width": self.expiry_min_credit_to_width,
            "expiry_position_risk": self.expiry_position_risk,
        }

        for name, value in fractions.items():
            if not 0.0 <= value <= 1.0:
                raise StrategyConfigurationError(
                    f"'{name}' must be between 0.0 and 1.0, got {value!r}."
                )

    def _validate_parameters(self) -> None:
        if self.shift_multiplier <= 0.0:
            raise StrategyConfigurationError("shift_multiplier must be positive.")

        if self.min_premium <= 0.0:
            raise StrategyConfigurationError("min_premium must be positive.")

        if self.min_body_premium_pct <= 0.0:
            raise StrategyConfigurationError(
                "min_body_premium_pct must be positive."
            )
        if self.min_credit_to_width <= 0.0:
            raise StrategyConfigurationError(
                "min_credit_to_width must be positive."
            )
        if self.expiry_min_credit_to_width <= 0.0:
            raise StrategyConfigurationError(
                "expiry_min_credit_to_width must be positive."
            )

        if self.hedge_enabled and self.hedge_wing_strikes <= 0:
            raise StrategyConfigurationError(
                "hedge_wing_strikes must be positive when hedging is enabled."
            )
