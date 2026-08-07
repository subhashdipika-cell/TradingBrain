"""
TradingBrain
Portfolio - Exposure

Aggregates net Greeks exposure across all open option positions. A theta
harvesting strategy lives and dies by its aggregate Greeks: net theta is the
income, net delta/gamma is the directional risk that must be kept in check.

Author: TradingBrain
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from app.domains.market.option_chain import OptionChain
from app.domains.portfolio.position import Position


@dataclass(frozen=True, slots=True)
class GreeksExposure:
    """Net portfolio Greeks, scaled by signed quantity and lot size."""

    delta: float = 0.0
    gamma: float = 0.0
    theta: float = 0.0
    vega: float = 0.0
    rho: float = 0.0

    def __add__(self, other: "GreeksExposure") -> "GreeksExposure":
        return GreeksExposure(
            delta=self.delta + other.delta,
            gamma=self.gamma + other.gamma,
            theta=self.theta + other.theta,
            vega=self.vega + other.vega,
            rho=self.rho + other.rho,
        )


def position_exposure(position: Position, chain: OptionChain) -> GreeksExposure:
    """Greeks contribution of one option position given the current chain."""
    if not position.is_option or position.strike is None or position.right is None:
        return GreeksExposure()

    quote = chain.get(position.strike, position.right)
    if quote is None:
        return GreeksExposure()

    scale = position.quantity * position.multiplier
    g = quote.greeks
    return GreeksExposure(
        delta=g.delta * scale,
        gamma=g.gamma * scale,
        theta=g.theta * scale,
        vega=g.vega * scale,
        rho=g.rho * scale,
    )


def aggregate_exposure(
    positions: Iterable[Position], chain: OptionChain
) -> GreeksExposure:
    """Net Greeks across all open positions."""
    total = GreeksExposure()
    for position in positions:
        if position.is_open:
            total = total + position_exposure(position, chain)
    return total
