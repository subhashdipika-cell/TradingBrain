"""Tests for risk sizing, drawdown and the kill switch."""

from __future__ import annotations

from datetime import datetime

from app.domains.portfolio.portfolio import Portfolio
from app.domains.risk.drawdown import DrawdownTracker
from app.domains.risk.kill_switch import KillSwitch
from app.domains.risk.limits import RiskLimits
from app.domains.risk.position_sizing import PositionSizer
from app.domains.risk.risk_engine import RiskEngine
from app.domains.shared.enums import OptionRight


def test_margin_based_sizing():
    sizer = PositionSizer(default_margin_pct=0.12)
    res = sizer.size_for_premium_selling(
        capital=1_000_000, allocation_fraction=0.33, spot=25_000, lot_size=75
    )
    # margin/lot = 25000*75*0.12 = 225,000 -> budget 330,000 -> 1 lot
    assert res.lots == 1
    assert res.units == 75


def test_risk_based_sizing():
    sizer = PositionSizer()
    res = sizer.size_by_risk(
        capital=1_000_000, risk_fraction=0.02, stop_loss_points=100, lot_size=75
    )
    # risk budget 20,000 / (100*75=7500) -> 2 lots
    assert res.lots == 2


def test_drawdown_breach():
    dd = DrawdownTracker(max_drawdown_fraction=0.10)
    dd.update(1_000_000)
    dd.update(950_000)
    assert not dd.is_breached()
    dd.update(890_000)
    assert dd.is_breached()


def test_kill_switch_latches():
    ks = KillSwitch()
    ks.trip("test", datetime(2026, 1, 1))
    assert ks.is_active
    ks.trip("second", datetime(2026, 1, 2))  # no-op while active
    assert ks.reason == "test"
    ks.reset()
    assert ks.allow_new_entries()


def test_risk_engine_blocks_after_daily_loss():
    pf = Portfolio(1_000_000)
    engine = RiskEngine(RiskLimits(max_daily_loss=0.05))
    engine.start_session(pf.equity())

    pf.apply_fill(
        symbol="NIFTY",
        instrument="CE",
        quantity=-75,
        price=100.0,
        right=OptionRight.CALL,
        strike=25000,
    )
    pf.mark_instrument("CE", 100.0 + 800)  # large adverse move

    decision = engine.update(pf, datetime(2026, 1, 1, 12, 0))
    assert decision.kill_switch_tripped
    assert engine.approve_entry(pf).approved is False
