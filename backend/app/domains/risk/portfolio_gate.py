"""Portfolio-level pre-order risk controls.

This gate is deliberately independent of any strategy. It sizes defined-risk
credit structures before order generation and tracks realized plus unrealized
drawdown so the execution layer has one authoritative approval point.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from app.domains.portfolio.portfolio import Portfolio
from app.domains.risk.limits import RiskLimits
from app.domains.risk.position_sizing import PositionSizer, SpreadSizingResult
from app.domains.shared.enums import ExecutionMode


@dataclass(frozen=True, slots=True)
class GateDecision:
    approved: bool
    safe_lot_count: int = 0
    max_possible_loss: float = 0.0
    reason: str = ""
    adjusted_long_strike: float | None = None


class PortfolioRiskGate:
    """Hard pre-order and portfolio drawdown interceptor."""

    def __init__(
        self,
        limits: RiskLimits | None = None,
        *,
        sizer: PositionSizer | None = None,
    ) -> None:
        self.limits = limits or RiskLimits()
        self.sizer = sizer or PositionSizer(risk_fraction=self.limits.max_position_risk)
        self.execution_mode = ExecutionMode.BACKTEST
        self.entries_disabled = False
        self.paper_only = False
        self.reason = ""
        self._day: date | None = None
        self._week: tuple[int, int] | None = None
        self._day_start_equity: float | None = None
        self._week_start_equity: float | None = None

    def start_session(self, equity: float, when: datetime) -> None:
        """Initialize daily and weekly baselines without clearing a freeze."""
        current_week = (when.isocalendar().year, when.isocalendar().week)
        if self._week != current_week:
            self._week = current_week
            self._week_start_equity = equity
            self.paper_only = False
        if self._day != when.date():
            self._day = when.date()
            self._day_start_equity = equity
            self.entries_disabled = False
            self.reason = ""

    def update(self, portfolio: Portfolio, when: datetime) -> GateDecision:
        """Check combined realized and unrealized equity loss."""
        self.start_session(portfolio.equity(), when) if self._day is None else None
        equity = portfolio.equity()
        daily_loss = self._loss_fraction(equity, self._day_start_equity)
        weekly_loss = self._loss_fraction(equity, self._week_start_equity)
        if daily_loss >= self.limits.max_daily_loss:
            self.entries_disabled = True
            self.reason = f"daily drawdown {daily_loss:.2%} >= {self.limits.max_daily_loss:.2%}"
            return GateDecision(False, reason=self.reason)
        if weekly_loss >= self.limits.max_weekly_loss:
            self.entries_disabled = True
            self.paper_only = True
            self.execution_mode = ExecutionMode.PAPER
            self.reason = f"weekly drawdown {weekly_loss:.2%} >= {self.limits.max_weekly_loss:.2%}"
            return GateDecision(False, reason=self.reason)
        return GateDecision(True, reason="portfolio drawdown within limits")

    def validate_and_scale_order(
        self,
        portfolio: Portfolio,
        *,
        strategy_type: str,
        symbol: str,
        short_strike: float,
        long_strike: float,
        net_credit: float,
        requested_lots: int | None = None,
        lot_size: int | None = None,
        when: datetime | None = None,
    ) -> GateDecision:
        """Approve and size one defined-risk credit spread before API calls."""
        if when is not None:
            health = self.update(portfolio, when)
            if not health.approved:
                return health
        if self.entries_disabled:
            return GateDecision(False, reason=self.reason or "entries disabled")
        if self.paper_only:
            return GateDecision(False, reason="weekly circuit breaker: paper trading only")

        effective_long = self.sizer.adjust_hedge_strike(
            account_balance=portfolio.equity(),
            short_strike=short_strike,
            long_strike=long_strike,
            net_credit=net_credit,
            symbol=symbol,
            lot_size=lot_size,
        )
        result: SpreadSizingResult = self.sizer.size_credit_spread(
            account_balance=portfolio.equity(),
            strategy_type=strategy_type,
            short_strike=short_strike,
            long_strike=effective_long,
            net_credit=net_credit,
            symbol=symbol,
            lot_size=lot_size,
            requested_lots=requested_lots,
        )
        if not result.is_trade_allowed:
            return GateDecision(False, reason=result.reason, adjusted_long_strike=effective_long)
        return GateDecision(
            True,
            safe_lot_count=result.safe_lot_count,
            max_possible_loss=result.max_possible_loss,
            reason=result.reason,
            adjusted_long_strike=effective_long,
        )

    @staticmethod
    def _loss_fraction(equity: float, baseline: float | None) -> float:
        if baseline is None or baseline <= 0 or equity >= baseline:
            return 0.0
        return (baseline - equity) / baseline
