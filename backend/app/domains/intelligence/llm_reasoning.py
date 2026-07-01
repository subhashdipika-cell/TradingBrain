"""
TradingBrain
Intelligence - LLM Reasoning

An optional reasoning layer that turns the quantitative MarketContext into a
qualitative trade recommendation (trade / hold / avoid) with a rationale.

Two implementations:
- :class:`HeuristicReasoner` - transparent, offline default (no API key).
- :class:`ClaudeReasoner`    - live seam calling the Anthropic API.

The Claude seam is intentionally guarded: it lazily imports the ``anthropic``
SDK (not a hard dependency) and requires ANTHROPIC_API_KEY, so the platform
runs fully without it. Default model is the latest Opus (``claude-opus-4-8``).

Author: TradingBrain
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum

from app.domains.shared.enums import VolatilityRegime
from app.domains.strategy.contracts.context import MarketContext

# Latest Claude Opus model id; override per call if needed.
DEFAULT_CLAUDE_MODEL = "claude-opus-4-8"


class Recommendation(str, Enum):
    TRADE = "TRADE"
    HOLD = "HOLD"
    AVOID = "AVOID"


@dataclass(frozen=True, slots=True)
class ReasoningResult:
    recommendation: Recommendation
    confidence: float  # 0 .. 1
    rationale: str


class LLMReasoner(ABC):
    """Produces a qualitative recommendation for the current context."""

    @abstractmethod
    def reason(self, context: MarketContext) -> ReasoningResult:
        raise NotImplementedError


class HeuristicReasoner(LLMReasoner):
    """
    Offline reasoner approximating a 'should I sell premium now?' check for a
    theta strategy: favour calm, range-bound, non-event conditions.
    """

    def reason(self, context: MarketContext) -> ReasoningResult:
        if context.volatility_regime is VolatilityRegime.EXTREME:
            return ReasoningResult(
                Recommendation.AVOID, 0.9, "Extreme volatility - avoid short premium."
            )
        if abs(context.news_score) >= 0.5:
            return ReasoningResult(
                Recommendation.AVOID, 0.7, "High-impact news risk present."
            )
        if context.volatility_regime in (
            VolatilityRegime.LOW,
            VolatilityRegime.NORMAL,
        ):
            return ReasoningResult(
                Recommendation.TRADE,
                0.6,
                "Calm regime favourable for theta harvesting.",
            )
        return ReasoningResult(
            Recommendation.HOLD, 0.4, "Elevated volatility - wait for confirmation."
        )


class ClaudeReasoner(LLMReasoner):
    """
    Live reasoner backed by the Anthropic API (SCAFFOLD / live seam).

    Requires ``pip install anthropic`` and an ANTHROPIC_API_KEY. The request
    shape below is correct for the Messages API; the response parsing is left
    minimal on purpose - extend it (e.g. structured tool use) before relying
    on it for live decisions.
    """

    def __init__(
        self,
        *,
        model: str = DEFAULT_CLAUDE_MODEL,
        api_key: str | None = None,
        max_tokens: int = 512,
    ) -> None:
        self._model = model
        self._api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        self._max_tokens = max_tokens

    def reason(self, context: MarketContext) -> ReasoningResult:
        if not self._api_key:
            raise RuntimeError(
                "ClaudeReasoner requires ANTHROPIC_API_KEY. Use HeuristicReasoner "
                "for offline runs."
            )
        try:
            import anthropic  # lazy: not a hard dependency
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise RuntimeError(
                "The 'anthropic' package is not installed. Run "
                "`pip install anthropic` to use ClaudeReasoner."
            ) from exc

        client = anthropic.Anthropic(api_key=self._api_key)
        prompt = self._build_prompt(context)

        # TODO: switch to structured tool-use for a machine-parseable verdict
        # before using this in live trading.
        response = client.messages.create(
            model=self._model,
            max_tokens=self._max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        text = "".join(block.text for block in response.content if block.type == "text")
        return self._parse(text)

    # ------------------------------------------------------------------
    def _build_prompt(self, context: MarketContext) -> str:
        return (
            "You are a risk-aware options trading assistant for a theta "
            "harvesting (short straddle) strategy on Indian index options.\n"
            f"Symbol: {context.symbol}\n"
            f"Spot: {context.last_price}\n"
            f"Implied volatility: {context.implied_volatility:.2%}\n"
            f"Volatility regime: {context.volatility_regime.value}\n"
            f"Market regime: {context.market_regime.value}\n"
            f"Sentiment: {context.sentiment_score:+.2f}  "
            f"News: {context.news_score:+.2f}\n"
            "Reply on one line as: TRADE|HOLD|AVOID <confidence 0-1> <reason>."
        )

    def _parse(self, text: str) -> ReasoningResult:
        token = text.strip().split()
        if not token:
            return ReasoningResult(Recommendation.HOLD, 0.0, "Empty response.")
        verdict = token[0].upper()
        try:
            recommendation = Recommendation(verdict)
        except ValueError:
            recommendation = Recommendation.HOLD
        confidence = 0.5
        if len(token) > 1:
            try:
                confidence = max(0.0, min(1.0, float(token[1])))
            except ValueError:
                pass
        rationale = " ".join(token[2:]) if len(token) > 2 else text.strip()
        return ReasoningResult(recommendation, confidence, rationale)
