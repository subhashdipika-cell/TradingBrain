"""
TradingBrain

TB008 - Risk Layer

Validates a proposed structure and decides when to exit. The philosophy is the
"safe feeling": keep MTM swings small and bank a modest ~1% weekly profit early
rather than holding to expiry.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from app.domains.strategy.tb008.configuration import TB008Configuration
from app.domains.strategy.tb008.models import CalendarStructure, PayoffProfile


class ExitDecision(str, Enum):
    HOLD = "HOLD"
    PROFIT_TARGET = "PROFIT_TARGET"
    MAX_LOSS = "MAX_LOSS"
    MTM_SWING = "MTM_SWING"
    RANGE_BREACH = "RANGE_BREACH"


@dataclass(frozen=True, slots=True)
class RiskDecision:
    approved: bool
    reason: str


class RiskLayer:
    def __init__(self, config: TB008Configuration) -> None:
        self.config = config

    def validate(
        self, structure: CalendarStructure, payoff: PayoffProfile
    ) -> RiskDecision:
        """Accept the structure only if it is genuinely low-swing income."""
        if payoff.max_profit <= 0:
            return RiskDecision(False, "no positive expectancy in range")
        if payoff.profit_low is None or payoff.profit_high is None:
            return RiskDecision(False, "no profitable band")

        # Loss must stay within the configured multiple of margin.
        if abs(payoff.max_loss) > self.config.max_loss_pct * payoff.margin * 3:
            return RiskDecision(False, "max loss exceeds risk budget")

        # The profitable band must at least cover the expected weekly range.
        needed = structure.spot * self.config.weekly_range_pct
        if (payoff.profit_high - payoff.profit_low) < needed:
            return RiskDecision(False, "profit band narrower than weekly range")

        return RiskDecision(True, "approved")

    def should_exit(
        self,
        *,
        current_pnl: float,
        margin: float,
        spot: float,
        payoff: PayoffProfile,
    ) -> ExitDecision:
        """
        Exit rules, evaluated on the open position each bar:

        - Bank ~1% of margin in hand -> take it and leave.
        - Cap the loss and the MTM swing.
        - Bail if price has breached the profitable range.
        """
        if margin <= 0:
            return ExitDecision.HOLD

        if current_pnl >= self.config.weekly_profit_target_pct * margin:
            return ExitDecision.PROFIT_TARGET
        if current_pnl <= -self.config.max_loss_pct * margin:
            return ExitDecision.MAX_LOSS
        if current_pnl <= -self.config.max_mtm_swing_pct * margin:
            return ExitDecision.MTM_SWING
        if payoff.profit_low is not None and payoff.profit_high is not None:
            if spot < payoff.profit_low or spot > payoff.profit_high:
                return ExitDecision.RANGE_BREACH
        return ExitDecision.HOLD
