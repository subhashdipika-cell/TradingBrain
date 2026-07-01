"""
TradingBrain
Intelligence - Parameter Optimizer

A generic grid-search optimizer. It is deliberately decoupled from the
backtest runner: the caller supplies an ``objective`` callable that maps a
parameter dict to a score (e.g. run a backtest and return Sharpe or net
return). This keeps the intelligence domain free of application-layer
dependencies while still providing a real, usable optimizer.

Author: TradingBrain
"""

from __future__ import annotations

import itertools
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

Objective = Callable[[dict[str, Any]], float]


@dataclass(frozen=True, slots=True)
class OptimizationResult:
    best_params: dict[str, Any]
    best_score: float
    evaluated: int
    leaderboard: list[tuple[dict[str, Any], float]]


class GridSearchOptimizer:
    """Exhaustive grid search over a discrete parameter space."""

    def __init__(self, space: dict[str, Sequence[Any]]) -> None:
        if not space:
            raise ValueError("Parameter space must be non-empty.")
        self._space = space

    def combinations(self) -> list[dict[str, Any]]:
        keys = list(self._space.keys())
        return [
            dict(zip(keys, values))
            for values in itertools.product(*self._space.values())
        ]

    def optimize(
        self, objective: Objective, *, maximize: bool = True, top_n: int = 10
    ) -> OptimizationResult:
        """Evaluate every combination and return the best by ``objective``."""
        scored: list[tuple[dict[str, Any], float]] = []
        for params in self.combinations():
            scored.append((params, objective(params)))

        scored.sort(key=lambda item: item[1], reverse=maximize)
        best_params, best_score = scored[0]
        return OptimizationResult(
            best_params=best_params,
            best_score=best_score,
            evaluated=len(scored),
            leaderboard=scored[:top_n],
        )
