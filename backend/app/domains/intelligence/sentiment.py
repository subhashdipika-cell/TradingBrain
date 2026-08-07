"""
TradingBrain
Intelligence - Sentiment

Sentiment providers return a score in [-1, +1] for a symbol. The default is
neutral (0.0) so the platform runs with no external dependency; a keyword
provider is included for offline use, and real providers (broker analytics,
social feeds, an LLM) can implement the same interface.

Author: TradingBrain
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.domains.shared.utils import clamp


class SentimentProvider(ABC):
    """Returns a sentiment score in [-1, +1] for a symbol."""

    @abstractmethod
    def score(self, symbol: str) -> float:
        raise NotImplementedError


class NeutralSentimentProvider(SentimentProvider):
    """Always-neutral default (no external dependency)."""

    def score(self, symbol: str) -> float:
        return 0.0


class KeywordSentimentProvider(SentimentProvider):
    """
    Offline lexicon sentiment over headlines fed in per symbol.

    Useful for tests and as a template for a real NLP/LLM provider.
    """

    _POSITIVE = {"surge", "rally", "beat", "upgrade", "bullish", "gain"}
    _NEGATIVE = {"crash", "plunge", "miss", "downgrade", "bearish", "loss"}

    def __init__(self) -> None:
        self._headlines: dict[str, list[str]] = {}

    def add_headline(self, symbol: str, headline: str) -> None:
        self._headlines.setdefault(symbol.upper(), []).append(headline)

    def score(self, symbol: str) -> float:
        headlines = self._headlines.get(symbol.upper(), [])
        if not headlines:
            return 0.0
        net = 0
        for headline in headlines:
            words = {w.strip(".,!?").lower() for w in headline.split()}
            net += len(words & self._POSITIVE) - len(words & self._NEGATIVE)
        return clamp(net / len(headlines), -1.0, 1.0)
