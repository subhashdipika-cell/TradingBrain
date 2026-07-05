"""
TradingBrain
Analytics - Trade Statistics

Pure functions computing the standard trade-quality metrics from a list of
trade PnLs: win rate, profit factor, expectancy, average win/loss. No state,
no side effects - easy to unit-test and reuse.

Author: TradingBrain
"""

from __future__ import annotations

from dataclasses import dataclass

from app.domains.shared.utils import safe_div


@dataclass(frozen=True, slots=True)
class TradeStatistics:
    total_trades: int = 0
    wins: int = 0
    losses: int = 0
    win_rate: float = 0.0
    gross_profit: float = 0.0
    gross_loss: float = 0.0
    net_profit: float = 0.0
    profit_factor: float = 0.0
    average_win: float = 0.0
    average_loss: float = 0.0
    expectancy: float = 0.0
    largest_win: float = 0.0
    largest_loss: float = 0.0


def compute_statistics(pnls: list[float]) -> TradeStatistics:
    """Compute trade statistics from realized trade PnLs."""
    if not pnls:
        return TradeStatistics()

    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]

    gross_profit = sum(wins)
    gross_loss = sum(losses)  # negative or zero
    net_profit = gross_profit + gross_loss

    win_rate = safe_div(len(wins), len(pnls))
    average_win = safe_div(gross_profit, len(wins))
    average_loss = safe_div(gross_loss, len(losses))
    expectancy = safe_div(net_profit, len(pnls))
    profit_factor = safe_div(gross_profit, abs(gross_loss), default=float("inf"))

    return TradeStatistics(
        total_trades=len(pnls),
        wins=len(wins),
        losses=len(losses),
        win_rate=win_rate,
        gross_profit=gross_profit,
        gross_loss=gross_loss,
        net_profit=net_profit,
        profit_factor=profit_factor,
        average_win=average_win,
        average_loss=average_loss,
        expectancy=expectancy,
        largest_win=max(wins, default=0.0),
        largest_loss=min(losses, default=0.0),
    )
