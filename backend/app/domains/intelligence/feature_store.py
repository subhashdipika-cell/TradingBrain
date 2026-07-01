"""
TradingBrain
Intelligence - Feature Store

A lightweight in-memory store of named numeric features keyed by timestamp.
Strategies and models read features through one interface regardless of how
they were produced (indicators, sentiment, model outputs). A persistent
backend (Redis / Postgres) can implement the same interface later.

Author: TradingBrain
"""

from __future__ import annotations

from collections import defaultdict, deque
from datetime import datetime


class FeatureStore:
    """In-memory rolling store of named features."""

    def __init__(self, maxlen: int = 5_000) -> None:
        self._values: dict[str, deque[tuple[datetime, float]]] = defaultdict(
            lambda: deque(maxlen=maxlen)
        )

    def set(self, name: str, timestamp: datetime, value: float) -> None:
        self._values[name].append((timestamp, value))

    def set_many(self, timestamp: datetime, features: dict[str, float]) -> None:
        for name, value in features.items():
            self.set(name, timestamp, value)

    def latest(self, name: str) -> float | None:
        series = self._values.get(name)
        if not series:
            return None
        return series[-1][1]

    def history(self, name: str) -> list[tuple[datetime, float]]:
        return list(self._values.get(name, ()))

    def names(self) -> list[str]:
        return sorted(self._values.keys())

    def snapshot(self) -> dict[str, float]:
        """Latest value of every known feature."""
        return {name: series[-1][1] for name, series in self._values.items() if series}
