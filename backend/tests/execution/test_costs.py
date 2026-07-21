"""Tests for the Indian options transaction-cost model."""

from __future__ import annotations

from app.application.backtest import BacktestConfig, run_backtest
from app.domains.execution.costs import (
    CostRates,
    FlatCostModel,
    IndianOptionsCostModel,
)


def test_sell_incurs_stt_buy_does_not():
    model = IndianOptionsCostModel()
    sell = model.charge(price=100.0, units=75, is_buy=False)
    buy = model.charge(price=100.0, units=75, is_buy=True)
    # STT applies only on the sell side; stamp duty only on the buy side.
    assert sell.stt > 0
    assert buy.stt == 0
    assert buy.stamp > 0
    assert sell.stamp == 0


def test_costs_scale_with_turnover():
    model = IndianOptionsCostModel()
    small = model.charge(price=50.0, units=75, is_buy=False)
    big = model.charge(price=200.0, units=75, is_buy=False)
    assert big.total > small.total


def test_gst_is_18pct_of_brokerage_exchange_ipft_sebi():
    rates = CostRates()
    model = IndianOptionsCostModel(rates)
    c = model.charge(price=100.0, units=75, is_buy=False)
    expected_gst = rates.gst_pct * (c.brokerage + c.exchange + c.ipft + c.sebi)
    assert abs(c.gst - expected_gst) < 1e-9


def test_ipft_charged_on_both_sides_at_rs50_per_crore():
    rates = CostRates()
    model = IndianOptionsCostModel(rates)
    sell = model.charge(price=100.0, units=75, is_buy=False)
    buy = model.charge(price=100.0, units=75, is_buy=True)
    expected = rates.ipft_pct * 100.0 * 75
    assert abs(sell.ipft - expected) < 1e-9
    assert abs(buy.ipft - expected) < 1e-9
    # Rs 50 / crore of premium turnover.
    assert abs(rates.ipft_pct * 1_00_00_000 - 50.0) < 1e-6


def test_ipft_is_included_in_total():
    c = IndianOptionsCostModel().charge(price=100.0, units=75, is_buy=False)
    parts = c.brokerage + c.stt + c.exchange + c.ipft + c.sebi + c.stamp + c.gst
    assert abs(c.total - parts) < 1e-9
    assert c.ipft > 0


def test_flat_model_has_no_statutory_charges():
    c = FlatCostModel(per_order=20.0).charge(price=100.0, units=75, is_buy=False)
    assert c.brokerage == 20.0
    assert c.stt == 0 and c.exchange == 0 and c.gst == 0


def test_zero_units_or_price_is_free():
    model = IndianOptionsCostModel()
    assert model.charge(price=0.0, units=75, is_buy=False).total == 0.0
    assert model.charge(price=100.0, units=0, is_buy=False).total == 0.0


def test_costs_reduce_backtest_net_profit():
    base = dict(num_days=12, seed=5, base_iv=0.15, annual_vol=0.08)
    with_costs = run_backtest(BacktestConfig(include_costs=True, **base))
    without_costs = run_backtest(BacktestConfig(include_costs=False, **base))

    net_with = sum(with_costs.journal.pnls())
    net_without = sum(without_costs.journal.pnls())
    total_costs = sum(t.commission for t in with_costs.journal.trades)

    assert total_costs > 0
    # Net with costs must be lower, by roughly the total costs charged.
    assert net_with < net_without
    assert abs((net_without - net_with) - total_costs) < 1.0
