"""Tests for the intelligence domain (enricher, reasoner, optimizer)."""

from __future__ import annotations

from datetime import datetime

import pytest

from app.domains.intelligence.llm_reasoning import (
    ClaudeReasoner,
    HeuristicReasoner,
    Recommendation,
)
from app.domains.intelligence.market_context import MarketContextEnricher
from app.domains.intelligence.optimizer import GridSearchOptimizer
from app.domains.shared.enums import ExecutionMode, VolatilityRegime
from app.domains.strategy.contracts.context import MarketContext


def _context(**kwargs) -> MarketContext:
    base = dict(
        symbol="NIFTY",
        exchange="NSE",
        timeframe="5m",
        timestamp=datetime(2026, 6, 30, 9, 25),
        execution_mode=ExecutionMode.BACKTEST,
    )
    base.update(kwargs)
    return MarketContext(**base)


def test_enricher_sets_regime_and_trend():
    ctx = _context(
        volatility_regime=VolatilityRegime.NORMAL,
        adx=10,
        ema_fast=25050,
        ema_slow=25000,
    )
    MarketContextEnricher().enrich(ctx)
    assert ctx.market_regime.value in {"RANGING", "TRENDING", "VOLATILE", "UNKNOWN"}
    assert ctx.confidence >= 0.0


def test_heuristic_reasoner_avoids_extreme_vol():
    ctx = _context(volatility_regime=VolatilityRegime.EXTREME)
    result = HeuristicReasoner().reason(ctx)
    assert result.recommendation is Recommendation.AVOID


def test_heuristic_reasoner_trades_calm():
    ctx = _context(volatility_regime=VolatilityRegime.NORMAL)
    assert HeuristicReasoner().reason(ctx).recommendation is Recommendation.TRADE


def test_grid_search_optimizer():
    opt = GridSearchOptimizer({"a": [1, 2, 3], "b": [10, 20]})
    result = opt.optimize(lambda p: p["a"] * p["b"], maximize=True)
    assert result.best_params == {"a": 3, "b": 20}
    assert result.evaluated == 6


def test_claude_reasoner_requires_key():
    ctx = _context()
    with pytest.raises(RuntimeError):
        ClaudeReasoner(api_key=None).reason(ctx)
