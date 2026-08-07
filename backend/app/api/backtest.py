"""
TradingBrain
API - Backtest

Exposes the TB001 backtest runner over HTTP for the frontend. The run is
CPU-bound, so it is executed in a threadpool to avoid blocking the event loop.
"""

from __future__ import annotations

import os

from fastapi import APIRouter, HTTPException
from fastapi.concurrency import run_in_threadpool

from app.application.backtest import (
    BacktestConfig,
    BacktestResult,
    run_backtest,
    run_dhan_backtest,
)
from app.application.results_store import ResultsStore
from app.core.config import settings
from app.domains.analytics.reports import build_summary
from app.domains.market.symbol import is_supported, supported_symbols
from app.schemas.backtest import (
    BacktestRequest,
    BacktestResponse,
    EquityPointModel,
    EquitySummary,
    TradeModel,
    TradeSummary,
)

router = APIRouter(tags=["Backtest"])

_store = ResultsStore(settings.RESULTS_DIR)


def _build_response(
    request: BacktestRequest, result: BacktestResult
) -> BacktestResponse:
    journal = result.journal
    summary = build_summary(journal)
    return BacktestResponse(
        request=request,
        trades_summary=TradeSummary(**summary["trades"]),
        equity_summary=EquitySummary(**summary["equity"]),
        equity_curve=[
            EquityPointModel(timestamp=p.timestamp, equity=p.equity)
            for p in journal.equity_curve
        ],
        trades=[
            TradeModel(
                symbol=t.symbol,
                structure=t.structure,
                entry_time=t.entry_time,
                exit_time=t.exit_time,
                pnl=t.pnl,
                exit_reason=t.exit_reason,
                lots=t.lots,
            )
            for t in journal.trades
        ],
        report=result.report,
    )


@router.get("/backtest/symbols")
async def list_symbols() -> dict[str, object]:
    """Return the instruments available for backtesting + real-data status."""
    data_dir = settings.DHAN_DATA_DIR
    return {
        "symbols": supported_symbols(),
        "dhan_data_available": bool(data_dir and os.path.isdir(data_dir)),
    }


@router.get("/backtest/strategies")
async def list_strategies() -> dict[str, object]:
    """Available strategies for back/forward testing. AUTO = structure-aware
    regime selection; the rest are individual option-selling strategies."""
    from app.domains.strategy.contracts.registry import StrategyRegistry
    from app.domains.strategy.selector import register_all_strategies

    register_all_strategies()
    items = [{"name": "AUTO", "description": "Auto-select by market structure/regime"}]
    for name in StrategyRegistry.list():
        items.append({"name": name, "description": StrategyRegistry.get(name).description})
    return {"strategies": items}


@router.post("/backtest/run", response_model=BacktestResponse)
async def run(request: BacktestRequest) -> BacktestResponse:
    """Run a TB001 backtest on synthetic data and return metrics + report."""
    symbol = request.symbol.upper()
    if not is_supported(symbol):
        symbol = "NIFTY"

    config = BacktestConfig(
        symbol=symbol,
        num_days=request.num_days,
        bar_minutes=request.bar_minutes,
        starting_capital=request.starting_capital,
        base_iv=request.base_iv,
        annual_vol=request.annual_vol,
        seed=request.seed,
        strategy=request.strategy,
    )
    result = await run_in_threadpool(run_backtest, config)
    _store.save(
        run_type="backtest",
        symbol=symbol,
        journal=result.journal,
        report=result.report,
        params=request.model_dump(),
    )
    return _build_response(request, result)


@router.post("/backtest/dhan", response_model=BacktestResponse)
async def run_dhan(request: BacktestRequest) -> BacktestResponse:
    """
    Run a TB001 backtest on REAL Dhan option data from the server-configured
    ``DHAN_DATA_DIR`` (e.g. AlphaEdge's strategy-lab/data/options).
    """
    data_dir = settings.DHAN_DATA_DIR
    if not data_dir or not os.path.isdir(data_dir):
        raise HTTPException(
            status_code=400,
            detail="DHAN_DATA_DIR is not configured or does not exist. Set it "
            "in the backend .env to your Dhan options data directory.",
        )

    symbol = request.symbol.upper()
    if not is_supported(symbol):
        symbol = "NIFTY50"

    def _run() -> BacktestResult:
        return run_dhan_backtest(
            directory=data_dir,
            symbol=symbol,
            starting_capital=request.starting_capital,
            bar_minutes=request.bar_minutes,
            strategy=request.strategy,
        )

    try:
        result = await run_in_threadpool(_run)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    _store.save(
        run_type="dhan-backtest",
        symbol=symbol,
        journal=result.journal,
        report=result.report,
        params=request.model_dump(),
    )
    return _build_response(request, result)
