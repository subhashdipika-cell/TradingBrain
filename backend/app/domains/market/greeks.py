"""
TradingBrain
Market - Option Pricing & Greeks (Black-Scholes-Merton)

A dependency-free Black-Scholes-Merton implementation used to price index
options and compute their Greeks. This is the analytical core behind theta
harvesting: it lets the platform value a short straddle and track how its
theta/delta/gamma evolve intraday and toward expiry, without relying on a
live option-chain feed.

All Greeks are returned in trader-friendly units:
- ``delta``  : per 1.0 move in the underlying.
- ``gamma``  : delta change per 1.0 move in the underlying.
- ``theta``  : premium decay per **calendar day** (negative for long options).
- ``vega``   : premium change per **1 percentage point** (1%) change in IV.
- ``rho``    : premium change per **1 percentage point** change in rates.

Author: TradingBrain
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from app.domains.shared.enums import OptionRight

_SQRT_2PI = math.sqrt(2.0 * math.pi)
_DAYS_PER_YEAR = 365.0


def _norm_pdf(x: float) -> float:
    return math.exp(-0.5 * x * x) / _SQRT_2PI


def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


@dataclass(frozen=True, slots=True)
class OptionGreeks:
    """Price and Greeks for a single option contract."""

    price: float
    delta: float
    gamma: float
    theta: float  # per calendar day
    vega: float  # per 1% IV
    rho: float  # per 1% rate

    @property
    def intrinsic(self) -> float:  # pragma: no cover - convenience
        return max(self.price, 0.0)


def _intrinsic(right: OptionRight, spot: float, strike: float) -> float:
    if right is OptionRight.CALL:
        return max(spot - strike, 0.0)
    return max(strike - spot, 0.0)


def black_scholes(
    *,
    right: OptionRight,
    spot: float,
    strike: float,
    time_to_expiry: float,
    volatility: float,
    rate: float = 0.065,
    dividend_yield: float = 0.0,
) -> OptionGreeks:
    """
    Price an option and compute its Greeks via Black-Scholes-Merton.

    Parameters
    ----------
    right:
        CALL or PUT.
    spot:
        Current underlying price.
    strike:
        Option strike.
    time_to_expiry:
        Time to expiry in **years** (e.g. 1 trading day ~= 1/365).
    volatility:
        Annualized implied volatility as a fraction (0.15 == 15%).
    rate:
        Risk-free rate as a fraction. Default ~6.5% (India).
    dividend_yield:
        Continuous dividend yield as a fraction (0 for index options).

    Notes
    -----
    For degenerate inputs (expiry/vol <= 0) the option is priced at its
    intrinsic value with zero time-sensitivity Greeks.
    """
    if time_to_expiry <= 0.0 or volatility <= 0.0 or spot <= 0.0 or strike <= 0.0:
        price = _intrinsic(right, spot, strike)
        delta = 0.0
        if time_to_expiry <= 0.0 and price > 0.0:
            delta = 1.0 if right is OptionRight.CALL else -1.0
        return OptionGreeks(
            price=price, delta=delta, gamma=0.0, theta=0.0, vega=0.0, rho=0.0
        )

    sqrt_t = math.sqrt(time_to_expiry)
    sigma_sqrt_t = volatility * sqrt_t

    d1 = (
        math.log(spot / strike)
        + (rate - dividend_yield + 0.5 * volatility * volatility) * time_to_expiry
    ) / sigma_sqrt_t
    d2 = d1 - sigma_sqrt_t

    disc_r = math.exp(-rate * time_to_expiry)
    disc_q = math.exp(-dividend_yield * time_to_expiry)
    pdf_d1 = _norm_pdf(d1)

    # Greeks common to both rights
    gamma = (disc_q * pdf_d1) / (spot * sigma_sqrt_t)
    vega = spot * disc_q * pdf_d1 * sqrt_t  # per 1.0 vol

    if right is OptionRight.CALL:
        nd1 = _norm_cdf(d1)
        nd2 = _norm_cdf(d2)
        price = spot * disc_q * nd1 - strike * disc_r * nd2
        delta = disc_q * nd1
        theta_year = (
            -(spot * disc_q * pdf_d1 * volatility) / (2.0 * sqrt_t)
            - rate * strike * disc_r * nd2
            + dividend_yield * spot * disc_q * nd1
        )
        rho = strike * time_to_expiry * disc_r * nd2
    else:
        n_neg_d1 = _norm_cdf(-d1)
        n_neg_d2 = _norm_cdf(-d2)
        price = strike * disc_r * n_neg_d2 - spot * disc_q * n_neg_d1
        delta = -disc_q * n_neg_d1
        theta_year = (
            -(spot * disc_q * pdf_d1 * volatility) / (2.0 * sqrt_t)
            + rate * strike * disc_r * n_neg_d2
            - dividend_yield * spot * disc_q * n_neg_d1
        )
        rho = -strike * time_to_expiry * disc_r * n_neg_d2

    return OptionGreeks(
        price=max(price, 0.0),
        delta=delta,
        gamma=gamma,
        theta=theta_year / _DAYS_PER_YEAR,  # per calendar day
        vega=vega / 100.0,  # per 1% IV
        rho=rho / 100.0,  # per 1% rate
    )


def implied_volatility(
    *,
    right: OptionRight,
    market_price: float,
    spot: float,
    strike: float,
    time_to_expiry: float,
    rate: float = 0.065,
    dividend_yield: float = 0.0,
    tol: float = 1e-4,
    max_iter: int = 100,
) -> float:
    """
    Recover implied volatility from a market price via bisection.

    Bisection is used (not Newton) for robustness near-the-money and at
    short expiries where vega collapses. Returns ``0.0`` if the price is
    below intrinsic or a root cannot be bracketed.
    """
    intrinsic = _intrinsic(right, spot, strike)
    if market_price <= intrinsic or time_to_expiry <= 0.0:
        return 0.0

    low, high = 1e-4, 5.0  # 0.01% .. 500% vol

    def price_at(vol: float) -> float:
        return black_scholes(
            right=right,
            spot=spot,
            strike=strike,
            time_to_expiry=time_to_expiry,
            volatility=vol,
            rate=rate,
            dividend_yield=dividend_yield,
        ).price

    if price_at(high) < market_price:
        return high

    for _ in range(max_iter):
        mid = 0.5 * (low + high)
        diff = price_at(mid) - market_price
        if abs(diff) < tol:
            return mid
        if diff > 0:
            high = mid
        else:
            low = mid

    return 0.5 * (low + high)
