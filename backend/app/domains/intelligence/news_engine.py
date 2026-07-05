"""
TradingBrain
Intelligence - News Engine

Surfaces market-moving news/events to the platform. The default provider
returns nothing (so the system runs offline); a static provider supports
backtests with a known event calendar (e.g. RBI policy, expiry, results).
Live providers (RSS, broker news, an LLM summarizer) implement the same
interface.

Author: TradingBrain
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class NewsItem:
    timestamp: datetime
    symbol: str
    headline: str
    impact: float  # -1 (bearish) .. +1 (bullish)
    source: str = "unknown"


class NewsProvider(ABC):
    """Returns relevant news items for a symbol around a moment."""

    @abstractmethod
    def items(self, symbol: str, at: datetime) -> list[NewsItem]:
        raise NotImplementedError

    def has_high_impact(
        self, symbol: str, at: datetime, threshold: float = 0.5
    ) -> bool:
        return any(abs(i.impact) >= threshold for i in self.items(symbol, at))


class NullNewsProvider(NewsProvider):
    """Default no-news provider."""

    def items(self, symbol: str, at: datetime) -> list[NewsItem]:
        return []


class StaticNewsProvider(NewsProvider):
    """Replays a fixed list of news items (for backtests/tests)."""

    def __init__(self, items: list[NewsItem] | None = None) -> None:
        self._items = items or []

    def add(self, item: NewsItem) -> None:
        self._items.append(item)

    def items(self, symbol: str, at: datetime) -> list[NewsItem]:
        sym = symbol.upper()
        return [
            i
            for i in self._items
            if i.symbol.upper() == sym and i.timestamp.date() == at.date()
        ]
