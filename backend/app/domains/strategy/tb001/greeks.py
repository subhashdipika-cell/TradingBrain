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

    def gamma_per_pct(
        self,
        snapshot: GreeksSnapshot,
        spot: float,
    ) -> float:
        """
        Delta change per 1% move in the underlying - the practical read of
        gamma risk for a short-premium structure.

        Raw gamma scales as 1/S, so a NIFTY ATM straddle sits around 0.002
        while an equity option can be 100x that. Normalising by spot makes
        the number comparable across underlyings AND across expiries:

            ~0.4 at 7 DTE | ~0.6 at 3 DTE | ~1.1 at 1 DTE | ~2.0 intraday-expiry
        """
        if spot <= 0:
            return 0.0
        return abs(snapshot.gamma) * spot * 0.01

    def is_high_gamma(
        self,
        snapshot: GreeksSnapshot,
        spot: float | None = None,
        threshold: float = 0.8,
    ) -> bool:
        """
        True when the ATM straddle's delta would move by >= ``threshold`` per
        1% move in the underlying.

        The default 0.8 starts firing roughly inside the last two sessions of
        an expiry - exactly where a short-gamma structure is most fragile.
        NOTE: the old signature compared RAW gamma against 0.10, which for an
        index (gamma ~0.002) could never be true - the gate was dead by
        arithmetic. Pass ``spot`` to use the normalised measure.
        """
        if spot is None or spot <= 0:
            return abs(snapshot.gamma) >= threshold
        return self.gamma_per_pct(snapshot, spot) >= threshold

    def is_high_delta(
        self,
        snapshot: GreeksSnapshot,
        threshold: float = 0.30,
    ) -> bool:
        """
        Determine whether portfolio delta exceeds the threshold.
        """
        return abs(snapshot.delta) >= threshold