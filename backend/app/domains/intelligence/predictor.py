"""
TradingBrain
Intelligence - Predictor

Short-horizon directional predictors. The default is a transparent momentum
rule; an ML model can implement the same :class:`Predictor` interface and be
swapped in without changing the strategy or engine.

A prediction is a direction plus a confidence in [0, 1].

Author: TradingBrain
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from app.domains.shared.enums import TrendDirection
from app.domains.shared.utils import clamp
from app.domains.strategy.contracts.context import MarketContext


@dataclass(frozen=True, slots=True)
class Prediction:
    direction: TrendDirection
    confidence: float  # 0 .. 1

    @property
    def is_actionable(self) -> bool:
        return self.direction is not TrendDirection.SIDEWAYS and self.confidence > 0.0


class Predictor(ABC):
    @abstractmethod
    def predict(self, context: MarketContext) -> Prediction:
        raise NotImplementedError


class MomentumPredictor(Predictor):
    """Direction from fast/slow EMA separation; confidence from its size."""

    def __init__(self, *, scale: float = 0.005) -> None:
        # `scale` maps relative EMA gap -> confidence (0.5% gap ~ full conf).
        self._scale = scale

    def predict(self, context: MarketContext) -> Prediction:
        fast = context.ema_fast
        slow = context.ema_slow
        if fast <= 0 or slow <= 0:
            return Prediction(TrendDirection.SIDEWAYS, 0.0)

        gap = (fast - slow) / slow
        confidence = clamp(abs(gap) / self._scale, 0.0, 1.0)

        if gap > 0:
            return Prediction(TrendDirection.BULLISH, confidence)
        if gap < 0:
            return Prediction(TrendDirection.BEARISH, confidence)
        return Prediction(TrendDirection.SIDEWAYS, 0.0)
