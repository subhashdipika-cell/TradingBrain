"""Tests for the portfolio aggregate and position accounting."""

from __future__ import annotations

from app.domains.portfolio.portfolio import Portfolio
from app.domains.portfolio.position import Position
from app.domains.shared.enums import OptionRight, PositionSide


def test_position_short_then_cover_realizes_pnl():
    pos = Position(symbol="NIFTY", instrument="NIFTY25000CE", quantity=0, avg_price=0.0)
    pos.apply_fill(-75, 93.0)  # sell to open
    assert pos.side is PositionSide.SHORT
    pos.apply_fill(75, 70.0)  # buy to close
    assert pos.quantity == 0
    assert pos.realized_pnl == (93.0 - 70.0) * 75


def test_short_straddle_round_trip_profit():
    pf = Portfolio(starting_capital=1_000_000)
    pf.apply_fill(
        symbol="NIFTY",
        instrument="N25000CE",
        quantity=-75,
        price=93.0,
        right=OptionRight.CALL,
        strike=25000,
    )
    pf.apply_fill(
        symbol="NIFTY",
        instrument="N25000PE",
        quantity=-75,
        price=84.0,
        right=OptionRight.PUT,
        strike=25000,
    )

    pf.mark_instrument("N25000CE", 70.0)
    pf.mark_instrument("N25000PE", 60.0)
    assert pf.unrealized_pnl() == (93 - 70) * 75 + (84 - 60) * 75

    pf.apply_fill(
        symbol="NIFTY",
        instrument="N25000CE",
        quantity=75,
        price=70.0,
        right=OptionRight.CALL,
        strike=25000,
    )
    pf.apply_fill(
        symbol="NIFTY",
        instrument="N25000PE",
        quantity=75,
        price=60.0,
        right=OptionRight.PUT,
        strike=25000,
    )

    assert pf.realized_pnl() == 3525.0
    assert pf.has_open_positions is False
    assert pf.equity() == 1_000_000 + 3525.0


def test_average_price_on_scaling_in():
    pos = Position(symbol="NIFTY", instrument="X", quantity=0, avg_price=0.0)
    pos.apply_fill(-75, 100.0)
    pos.apply_fill(-75, 80.0)
    assert pos.quantity == -150
    assert pos.avg_price == 90.0
