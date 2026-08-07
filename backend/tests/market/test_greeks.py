"""Tests for the Black-Scholes pricing/greeks engine."""

from __future__ import annotations

import math

import pytest

from app.domains.market.greeks import black_scholes, implied_volatility
from app.domains.shared.enums import OptionRight

T = 7 / 365  # one week to expiry
SPOT = 25_000.0


def _call(strike: float, vol: float = 0.12):
    return black_scholes(
        right=OptionRight.CALL,
        spot=SPOT,
        strike=strike,
        time_to_expiry=T,
        volatility=vol,
    )


def _put(strike: float, vol: float = 0.12):
    return black_scholes(
        right=OptionRight.PUT,
        spot=SPOT,
        strike=strike,
        time_to_expiry=T,
        volatility=vol,
    )


def test_atm_prices_are_positive_and_close():
    call = _call(SPOT)
    put = _put(SPOT)
    assert call.price > 0 and put.price > 0
    # Near ATM, call and put premiums are comparable.
    assert abs(call.price - put.price) < call.price * 0.5


def test_long_options_have_negative_theta():
    assert _call(SPOT).theta < 0
    assert _put(SPOT).theta < 0


def test_call_delta_in_unit_interval_put_negative():
    assert 0.0 < _call(SPOT).delta < 1.0
    assert -1.0 < _put(SPOT).delta < 0.0


def test_put_call_parity_delta_relation():
    # delta_call - delta_put ~= 1 (no dividends)
    assert math.isclose(_call(SPOT).delta - _put(SPOT).delta, 1.0, abs_tol=1e-6)


def test_higher_vol_raises_premium():
    assert _call(SPOT, 0.20).price > _call(SPOT, 0.10).price


def test_implied_vol_roundtrip():
    price = _call(SPOT, 0.18).price
    iv = implied_volatility(
        right=OptionRight.CALL,
        market_price=price,
        spot=SPOT,
        strike=SPOT,
        time_to_expiry=T,
    )
    assert abs(iv - 0.18) < 0.01


def test_expired_option_is_intrinsic():
    g = black_scholes(
        right=OptionRight.CALL,
        spot=SPOT,
        strike=24_000,
        time_to_expiry=0.0,
        volatility=0.12,
    )
    assert g.price == pytest.approx(1000.0)
    assert g.theta == 0.0
