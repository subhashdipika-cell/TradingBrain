"""
TradingBrain
Schemas - Backtest API

Request/response models for the backtest endpoint consumed by the frontend.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class BacktestRequest(BaseModel):
    symbol: str = Field(default="NIFTY")
    num_days: int = Field(default=30, ge=1, le=120)
    bar_minutes: int = Field(default=5, ge=1, le=60)
    starting_capital: float = Field(default=1_000_000.0, gt=0)
    base_iv: float = Field(default=0.12, gt=0, le=2.0)
    annual_vol: float = Field(default=0.13, gt=0, le=2.0)
    seed: int = Field(default=42)
    # "AUTO" = structure-aware regime selection; or a specific TB001..TB006.
    strategy: str = Field(default="AUTO")


class TradeSummary(BaseModel):
    total: int
    wins: int
    losses: int
    win_rate: float
    profit_factor: float
    expectancy: float
    average_win: float
    average_loss: float
    largest_win: float
    largest_loss: float
    net_profit: float
    total_costs: float
    gross_profit_pre_cost: float


class EquitySummary(BaseModel):
    starting: float
    ending: float
    net_return: float
    return_pct: float
    max_drawdown: float
    max_drawdown_pct: float
    sharpe: float
    samples: int


class EquityPointModel(BaseModel):
    timestamp: datetime
    equity: float


class TradeModel(BaseModel):
    symbol: str
    structure: str
    entry_time: datetime
    exit_time: datetime
    pnl: float
    exit_reason: str
    lots: int


class BacktestResponse(BaseModel):
    request: BacktestRequest
    trades_summary: TradeSummary
    equity_summary: EquitySummary
    equity_curve: list[EquityPointModel]
    trades: list[TradeModel]
    report: str
