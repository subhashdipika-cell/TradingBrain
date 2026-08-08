"""Tests for fixed-fractional spread sizing and portfolio circuit breakers."""

from __future__ import annotations

from datetime import datetime

from app.domains.portfolio.portfolio import Portfolio
from app.domains.risk.limits import RiskLimits
from app.domains.risk.portfolio_gate import PortfolioRiskGate
from app.domains.risk.position_sizing import PositionSizer
from app.domains.shared.enums import OptionRight


def test_banknifty_spread_size_is_risk_based_and_capped() -> None:
    sizer = PositionSizer(risk_fraction=0.01, max_lots_per_trade=20)
    result = sizer.size_credit_spread(
        account_balance=1_000_000,
        strategy_type="IRON_CONDOR",
        short_strike=57_800,
        long_strike=58_000,
        net_credit=30,
        symbol="BANKNIFTY",
    )
    # (200 - 30) * 30 = Rs 5,100 per lot; Rs 10,000 budget permits one lot.
    assert result.safe_lot_count == 1
    assert result.max_possible_loss == 5_100
    assert result.is_trade_allowed


def test_wide_hedge_is_moved_closer_before_sizing() -> None:
    sizer = PositionSizer(risk_fraction=0.01)
    adjusted = sizer.adjust_hedge_strike(
        account_balance=1_000_000,
        short_strike=57_800,
        long_strike=58_300,
        net_credit=30,
        symbol="BANKNIFTY",
    )
    assert 57_800 < adjusted < 58_300


def test_daily_drawdown_blocks_and_trips_gate() -> None:
    portfolio = Portfolio(1_000_000)
    gate = PortfolioRiskGate(RiskLimits(max_daily_loss=0.025))
    when = datetime(2026, 8, 10, 10, 0)
    gate.start_session(portfolio.equity(), when)
    portfolio.apply_fill(
        symbol="BANKNIFTY",
        instrument="BANKNIFTY-57800CE",
        quantity=-30,
        price=100,
        right=OptionRight.CALL,
        strike=57_800,
    )
    portfolio.mark_instrument("BANKNIFTY-57800CE", 1_000)
    decision = gate.update(portfolio, when)
    assert not decision.approved
    assert gate.entries_disabled


def test_weekly_drawdown_switches_to_paper_mode() -> None:
    portfolio = Portfolio(1_000_000)
    limits = RiskLimits(max_daily_loss=1.0, max_weekly_loss=0.05)
    gate = PortfolioRiskGate(limits)
    when = datetime(2026, 8, 10, 10, 0)
    gate.start_session(portfolio.equity(), when)
    portfolio.apply_fill(
        symbol="NIFTY50",
        instrument="NIFTY50-25000CE",
        quantity=-65,
        price=100,
        right=OptionRight.CALL,
        strike=25_000,
    )
    portfolio.mark_instrument("NIFTY50-25000CE", 1_000)
    decision = gate.update(portfolio, when)
    assert not decision.approved
    assert gate.paper_only
