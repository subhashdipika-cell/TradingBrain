"""
TradingBrain

TB001 - Greeks Service
"""

from __future__ import annotations

from dataclasses import dataclass

from app.domains.strategy.contracts.context import MarketContext


@dataclass(slots=True)
class GreeksSnapshot:
    """
    Snapshot of the current option Greeks.
    """

    delta: float
    gamma: float
    theta: float
    vega: float
    rho: float


class GreeksService:
    """
    Provides a consistent interface for reading option Greeks.

    The source of Greeks (broker, exchange, or internal
    calculator) is intentionally hidden from the strategy.

    Future implementations may obtain Greeks from:
        - Dhan
        - Zerodha
        - NSE Option Chain
        - Internal Black-Scholes engine
    """

    def get_snapshot(
        self,
        context: MarketContext,
    ) -> GreeksSnapshot:
        """
        Build a Greeks snapshot from MarketContext.
        """

        return GreeksSnapshot(
            delta=context.delta,
            gamma=context.gamma,
            theta=context.theta,
            vega=context.vega,
            rho=context.rho,
        )

    def is_positive_theta(
        self,
        snapshot: GreeksSnapshot,
    ) -> bool:
        """
        Returns True when theta is positive.
        """
        return snapshot.theta > 0.0

    def is_high_gamma(
        self,
        snapshot: GreeksSnapshot,
        threshold: float = 0.10,
    ) -> bool:
        """
        Determine whether gamma exceeds the threshold.
        """
        return abs(snapshot.gamma) >= threshold

    def is_high_delta(
        self,
        snapshot: GreeksSnapshot,
        threshold: float = 0.30,
    ) -> bool:
        """
        Determine whether portfolio delta exceeds the threshold.
        """
        return abs(snapshot.delta) >= threshold