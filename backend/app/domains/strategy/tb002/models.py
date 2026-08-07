"""
TradingBrain

TB002 - ICT Setup Models
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Mapping

from app.domains.strategy.tb002.exceptions import InvalidSetupError


class ICTDirection(str, Enum):
    """Directional intent after the liquidity sweep and inversion."""

    BULLISH = "BULLISH"
    BEARISH = "BEARISH"

    @classmethod
    def from_value(cls, value: object) -> "ICTDirection":
        token = _normalise_token(value)
        if token in {"BULLISH", "BULL", "BUY", "LONG", "UP"}:
            return cls.BULLISH
        if token in {"BEARISH", "BEAR", "SELL", "SHORT", "DOWN"}:
            return cls.BEARISH
        raise InvalidSetupError(f"Unsupported ICT direction: {value!r}")


class LiquiditySide(str, Enum):
    """Liquidity pool swept before the reversal model is armed."""

    BUY_SIDE = "BUY_SIDE"
    SELL_SIDE = "SELL_SIDE"

    @classmethod
    def from_value(cls, value: object) -> "LiquiditySide":
        token = _normalise_token(value)
        if token in {"BUY_SIDE", "BUYSIDE", "BSL", "HIGH", "HIGHS"}:
            return cls.BUY_SIDE
        if token in {"SELL_SIDE", "SELLSIDE", "SSL", "LOW", "LOWS"}:
            return cls.SELL_SIDE
        raise InvalidSetupError(f"Unsupported liquidity side: {value!r}")


@dataclass(frozen=True, slots=True)
class LiquiditySweep:
    """Higher-timeframe liquidity sweep, such as a daily or monthly high."""

    side: LiquiditySide
    timeframe: str
    reference_price: float | None = None
    swept_price: float | None = None
    confirmed: bool = True

    @classmethod
    def from_value(cls, value: object) -> "LiquiditySweep":
        if isinstance(value, cls):
            return value
        data = _mapping(value, "sweep")
        return cls(
            side=LiquiditySide.from_value(data.get("side")),
            timeframe=str(data.get("timeframe", "")).strip(),
            reference_price=_optional_float(data.get("reference_price")),
            swept_price=_optional_float(data.get("swept_price")),
            confirmed=bool(data.get("confirmed", True)),
        )


@dataclass(frozen=True, slots=True)
class FairValueGap:
    """Fair value gap or inversion fair value gap layer."""

    direction: ICTDirection
    timeframe: str
    low: float | None = None
    high: float | None = None
    inverted: bool = False
    tapped: bool = False
    inside_parent: bool = False
    candles_to_invert: int | None = None

    @classmethod
    def from_value(cls, value: object, *, default_inverted: bool) -> "FairValueGap":
        if isinstance(value, cls):
            return value
        data = _mapping(value, "fair value gap")
        return cls(
            direction=ICTDirection.from_value(data.get("direction")),
            timeframe=str(data.get("timeframe", "")).strip(),
            low=_optional_float(data.get("low")),
            high=_optional_float(data.get("high")),
            inverted=bool(data.get("inverted", default_inverted)),
            tapped=bool(data.get("tapped", False)),
            inside_parent=bool(data.get("inside_parent", False)),
            candles_to_invert=_optional_int(data.get("candles_to_invert")),
        )


@dataclass(frozen=True, slots=True)
class LowerTimeframeTrigger:
    """One-minute or five-minute inversion confirmation."""

    direction: ICTDirection
    timeframe: str
    price: float | None = None
    low: float | None = None
    high: float | None = None
    confirmed: bool = True

    @classmethod
    def from_value(cls, value: object) -> "LowerTimeframeTrigger":
        if isinstance(value, cls):
            return value
        data = _mapping(value, "trigger")
        return cls(
            direction=ICTDirection.from_value(data.get("direction")),
            timeframe=str(data.get("timeframe", "")).strip(),
            price=_optional_float(data.get("price")),
            low=_optional_float(data.get("low")),
            high=_optional_float(data.get("high")),
            confirmed=bool(data.get("confirmed", True)),
        )


@dataclass(frozen=True, slots=True)
class ICTSetup:
    """
    Complete TB002 setup.

    The expected sequence is:
    liquidity sweep -> higher-timeframe IFVG -> pullback into 15m PDA/FVG
    -> one-minute or five-minute IFVG trigger.
    """

    direction: ICTDirection
    entry_price: float
    stop_loss: float
    external_target: float
    sweep: LiquiditySweep
    htf_inversion: FairValueGap
    pullback_gap: FairValueGap
    trigger: LowerTimeframeTrigger
    first_target: float | None = None
    runner_target: float | None = None
    setup_time: datetime | None = None
    notes: tuple[str, ...] = field(default_factory=tuple)

    @classmethod
    def from_metadata(
        cls,
        value: object,
        *,
        default_entry_price: float | None = None,
    ) -> "ICTSetup | None":
        if value is None:
            return None
        if isinstance(value, cls):
            return value

        data = _mapping(value, "tb002_setup")
        direction = ICTDirection.from_value(data.get("direction"))
        entry_price = _required_float(
            data.get("entry_price", default_entry_price), "entry_price"
        )
        return cls(
            direction=direction,
            entry_price=entry_price,
            stop_loss=_required_float(data.get("stop_loss"), "stop_loss"),
            external_target=_required_float(
                data.get("external_target", data.get("take_profit")),
                "external_target",
            ),
            sweep=LiquiditySweep.from_value(data.get("sweep")),
            htf_inversion=FairValueGap.from_value(
                data.get("htf_inversion"), default_inverted=True
            ),
            pullback_gap=FairValueGap.from_value(
                data.get("pullback_gap"), default_inverted=False
            ),
            trigger=LowerTimeframeTrigger.from_value(data.get("trigger")),
            first_target=_optional_float(data.get("first_target")),
            runner_target=_optional_float(data.get("runner_target")),
            setup_time=_optional_datetime(data.get("setup_time")),
            notes=_notes(data.get("notes")),
        )

    @property
    def initial_target(self) -> float:
        if self.first_target is not None:
            return self.first_target
        return self.external_target

    @property
    def expected_sweep_side(self) -> LiquiditySide:
        if self.direction is ICTDirection.BEARISH:
            return LiquiditySide.BUY_SIDE
        return LiquiditySide.SELL_SIDE

    def risk_points(self) -> float:
        if self.direction is ICTDirection.BEARISH:
            return self.stop_loss - self.entry_price
        return self.entry_price - self.stop_loss

    def reward_points(self, target: float | None = None) -> float:
        target = self.initial_target if target is None else target
        if self.direction is ICTDirection.BEARISH:
            return self.entry_price - target
        return target - self.entry_price

    def risk_reward(self, target: float | None = None) -> float:
        risk = self.risk_points()
        if risk <= 0:
            return 0.0
        return self.reward_points(target) / risk


def normalise_timeframe(value: str) -> str:
    token = value.strip().lower().replace(" ", "").replace("-", "")
    token = token.replace("minutes", "m").replace("minute", "m")
    token = token.replace("mins", "m").replace("min", "m")
    return token


def _mapping(value: object, label: str) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    raise InvalidSetupError(f"Expected '{label}' to be a mapping.")


def _normalise_token(value: object) -> str:
    return str(value).strip().upper().replace("-", "_").replace(" ", "_")


def _required_float(value: object, label: str) -> float:
    parsed = _optional_float(value)
    if parsed is None:
        raise InvalidSetupError(f"Missing required numeric field '{label}'.")
    return parsed


def _optional_float(value: object) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise InvalidSetupError(f"Expected numeric value, got {value!r}.") from exc


def _optional_int(value: object) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise InvalidSetupError(f"Expected integer value, got {value!r}.") from exc


def _optional_datetime(value: object) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except ValueError as exc:
            raise InvalidSetupError(f"Invalid setup_time: {value!r}.") from exc
    raise InvalidSetupError(f"Invalid setup_time: {value!r}.")


def _notes(value: object) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    if isinstance(value, tuple):
        return tuple(str(item) for item in value)
    if isinstance(value, list):
        return tuple(str(item) for item in value)
    return (str(value),)
