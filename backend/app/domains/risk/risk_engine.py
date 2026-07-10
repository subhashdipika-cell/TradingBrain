"""
TradingBrain
Risk - Risk Engine

The platform-level gatekeeper. Every entry signal passes through the Risk
Engine before it can become an order. It enforces drawdown, daily-loss,
exposure and activity limits, and trips the kill switch on hard breaches.

It is intentionally strategy-agnostic: TB001's own ``RiskLayer`` handles
strategy-specific rules; this engine protects the whole account.

Author: TradingBrain
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.domains.portfolio.portfolio import Portfolio
from app.domains.risk.drawdown import DrawdownTracker
from app.domains.risk.kill_switch import KillSwitch
from app.domains.risk.limits import RiskLimits


@dataclass(frozen=True, slots=True)
class RiskDecision:
    """Outcome of a risk evaluation."""

    approved: bool
    reason: str
    kill_switch_tripped: bool = False

    @classmethod
    def allow(cls, reason: str = "approved") -> "RiskDecision":
        return cls(approved=True, reason=reason)

    @classmethod
    def block(cls, reason: str, kill: bool = False) -> "RiskDecision":
        return cls(approved=False, reason=reason, kill_switch_tripped=kill)


class RiskEngine:
    """Account-level risk gatekeeper."""

    def __init__(self, limits: RiskLimits | None = None) -> None:
        self.limits = limits or RiskLimits()
        self.drawdown = DrawdownTracker(max_drawdown_fraction=self.limits.max_drawdown)
        self.kill_switch = KillSwitch()
        self._day_start_equity: float | None = None
        self._trades_today: int = 0

    # ------------------------------------------------------------------
    # Session lifecycle
    # ------------------------------------------------------------------
    def start_session(self, equity: float) -> None:
        self._day_start_equity = equity
        self._trades_today = 0
        self.drawdown.update(equity)

    def record_trade(self) -> None:
        self._trades_today += 1

    # ------------------------------------------------------------------
    # Continuous monitoring (called each tick)
    # ------------------------------------------------------------------
    def update(self, portfolio: Portfolio, when: datetime) -> RiskDecision:
        """Update trackers and trip the kill switch on hard breaches."""
        equity = portfolio.equity()
        self.drawdown.update(equity)

        if self.drawdown.is_breached():
            self.kill_switch.trip(
                f"Max drawdown breached "
                f"({self.drawdown.current_drawdown_fraction():.2%})",
                when,
            )
            return RiskDecision.block("max drawdown breached", kill=True)

        daily_loss = self.daily_loss_fraction(portfolio)
        if daily_loss >= self.limits.max_daily_loss:
            self.kill_switch.trip(f"Max daily loss breached ({daily_loss:.2%})", when)
            return RiskDecision.block("max daily loss breached", kill=True)

        return RiskDecision.allow("within limits")

    # ------------------------------------------------------------------
    # Entry gate (called before opening a position)
    # ------------------------------------------------------------------
    def approve_entry(
        self, portfolio: Portfolio, *, new_capital: float = 0.0, max_loss: float = 0.0
    ) -> RiskDecision:
        """Decide whether a new entry may proceed.

        ``max_loss`` is the position's worst-case rupee loss for defined-risk
        (hedged) structures - pass 0.0 for naked/margin-sized structures where
        margin isn't a loss bound. Callers must supply this so a hedged spread
        can never be sized past ``max_position_risk`` of capital (previously
        dead: nothing enforced it, which let a credit-spread's own
        ``capital_allocation`` size a single trade to risk 25% of capital -
        see the 2026-07-09 TB006 incident).
        """
        if not self.kill_switch.allow_new_entries():
            return RiskDecision.block(f"kill switch active: {self.kill_switch.reason}")

        if len(portfolio.open_positions()) >= self.limits.max_open_positions:
            return RiskDecision.block("max open positions reached")

        if self._trades_today >= self.limits.max_trades_per_day:
            return RiskDecision.block("max trades per day reached")

        cap = portfolio.capital.starting_capital
        if new_capital > cap * self.limits.max_capital_per_trade:
            return RiskDecision.block("trade exceeds per-trade capital limit")

        if max_loss > cap * self.limits.max_position_risk:
            return RiskDecision.block("trade's max loss exceeds per-position risk limit")

        return RiskDecision.allow("entry approved")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def daily_loss_fraction(self, portfolio: Portfolio) -> float:
        if not self._day_start_equity:
            return 0.0
        change = portfolio.equity() - self._day_start_equity
        if change >= 0:
            return 0.0
        return abs(change) / self._day_start_equity
