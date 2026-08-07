"""
TradingBrain
API - Backtest

Exposes the TB001 backtest runner over HTTP for the frontend. The run is
CPU-bound, so it is executed in a threadpool to avoid blocking the event loop.
"""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.concurrency import run_in_threadpool

from app.application.backtest import BacktestConfig, run_backtest
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


@router.get("/backtest/symbols")
async def list_symbols() -> dict[str, list[str]]:
    """Return the instruments available for backtesting."""
    return {"symbols": supported_symbols()}


@router.post("/backtest/run", response_model=BacktestResponse)
async def run(request: BacktestRequest) -> BacktestResponse:
    """Run a TB001 backtest and return performance metrics + report."""
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
    )

    result = await run_in_threadpool(run_backtest, config)
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
