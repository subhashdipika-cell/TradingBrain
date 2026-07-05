"""
TradingBrain

TB008 - Adaptive Calendar Spread Engine (ACSE)

Low-volatility calendar-spread income: sell a far-OTM (~2-delta) strangle on the
near expiry, hedge with a next-expiry ratio calendar to flatten MTM, analyse the
payoff, and bank a modest ~1% weekly profit early. A distinct philosophy from
TB001's dynamic theta harvesting.

Data requirement: TB008 trades a TWO-expiry structure, so it needs both the near
and the next-expiry option chains, supplied via
``context.metadata['option_chain']`` and ``['option_chain_far']``. When the far
chain is absent (e.g. the current single-expiry feed) it stands aside safely -
so it never mis-executes; a multi-expiry feed unlocks live execution.

Author: TradingBrain
"""

from __future__ import annotations

from datetime import time

from app.domains.market.option_chain import OptionChain
from app.domains.shared.enums import OrderSide, PositionSide, SignalType
from app.domains.strategy.contracts.context import MarketContext
from app.domains.strategy.contracts.signal import Signal
from app.domains.strategy.contracts.strategy import BaseStrategy
from app.domains.strategy.tb008.configuration import TB008Configuration
from app.domains.strategy.tb008.core_layer import CoreLayer
from app.domains.strategy.tb008.exceptions import StructureConstructionError
from app.domains.strategy.tb008.hedging_layer import HedgingLayer
from app.domains.strategy.tb008.models import CalendarStructure
from app.domains.strategy.tb008.payoff_engine import PayoffEngine
from app.domains.strategy.tb008.position_manager import PositionManager
from app.domains.strategy.tb008.regime import VixRegimeClassifier
from app.domains.strategy.tb008.risk_layer import RiskLayer
from app.domains.strategy.tb008.state_machine import StateMachine, TB008State


class TB008Strategy(BaseStrategy):
    """Adaptive Calendar Spread Engine."""

    name = "TB008"
    version = "1.0.0"
    description = "Adaptive Calendar Spread Engine (low-VIX calendar income)"

    def __init__(self, config: TB008Configuration | None = None) -> None:
        super().__init__()
        self.configuration = config or TB008Configuration()
        self.regime = VixRegimeClassifier(self.configuration)
        self.core = CoreLayer(self.configuration)
        self.hedging = HedgingLayer(self.configuration)
        self.risk = RiskLayer(self.configuration)
        self.payoff = PayoffEngine()
        self.positions = PositionManager(self.configuration)
        self.state_machine = StateMachine()
        self._position_open = False

    def initialize(self) -> None:
        self.enabled = True
        self.state.initialized = True

    def pre_market(self, context: MarketContext) -> None:
        return

    # ------------------------------------------------------------------
    def build_structure(
        self, context: MarketContext
    ) -> tuple[CalendarStructure, object] | None:
        """Assemble the double calendar + payoff, or ``None`` if not deployable."""
        near = context.metadata.get("option_chain")
        far = context.metadata.get("option_chain_far")
        if not isinstance(near, OptionChain) or not isinstance(far, OptionChain):
            return None  # needs both expiries; stand aside safely

        vix = context.vix or context.implied_volatility * 100.0
        assessment = self.regime.assess(vix)
        if not assessment.favorable:
            return None  # only deploy in low, non-expanding volatility

        lot_size = int(context.metadata.get("lot_size", 75))
        spot = context.last_price or near.underlying

        try:
            sold = self.core.build_short_strangle(near, lot_size)
            hedges = self.hedging.build_ratio_hedge(
                far, lot_size, expansion_risk=assessment.expansion_risk
            )
        except StructureConstructionError:
            return None

        structure = CalendarStructure(
            symbol=context.symbol,
            spot=spot,
            lot_size=lot_size,
            near_expiry=near.expiry,
            far_expiry=far.expiry,
            implied_vol=context.implied_volatility or (vix / 100.0),
            legs=sold + hedges,
        )
        profile = self.payoff.analyze(
            structure, band_pct=self.configuration.weekly_range_pct
        )
        return structure, profile

    def generate_signal(self, context: MarketContext) -> Signal | None:
        if not self.enabled or self._position_open:
            return None
        if not context.is_market_open or not self._within_entry_window(context):
            return None

        built = self.build_structure(context)
        if built is None:
            return None
        structure, profile = built

        decision = self.risk.validate(structure, profile)
        if not decision.approved:
            return None

        self._position_open = True
        self.state_machine.transition(TB008State.STRUCTURE_OPEN)

        return Signal(
            strategy=self.name,
            symbol=context.symbol,
            signal_type=SignalType.SELL,
            side=OrderSide.SELL,
            position_side=PositionSide.SHORT,
            requested_risk=self.configuration.max_margin_utilisation,
            confidence=0.75,
            score=profile.margin_efficiency,
            reason="Double-calendar income (low VIX)",
            tags=["TB008", "CALENDAR", "LOW_VIX"],
            metadata={
                "structure": "DOUBLE_CALENDAR",
                "requires_multi_expiry": True,
                "calendar_legs": [
                    {
                        "right": leg.right.value,
                        "strike": leg.strike,
                        "side": leg.side,
                        "expiry_bucket": leg.expiry_bucket,
                        "lots": leg.lots,
                    }
                    for leg in structure.legs
                ],
                "net_credit": profile.net_credit,
                "max_profit": profile.max_profit,
                "max_loss": profile.max_loss,
                "margin": profile.margin,
                # Bank ~1% of margin in hand, then leave (the source method).
                "profit_target": profile.margin
                * self.configuration.weekly_profit_target_pct,
                "margin_efficiency": profile.margin_efficiency,
                "mtm_smoothness": profile.mtm_smoothness,
                "range_coverage_pct": profile.range_coverage_pct,
                "breakevens": list(profile.breakevens),
                "profit_low": profile.profit_low,
                "profit_high": profile.profit_high,
            },
        )

    def manage_position(self, context: MarketContext) -> Signal | None:
        # Exit/adjustment decisions require the marked structure PnL, which a
        # multi-expiry execution layer supplies. Kept as an extension point.
        return None

    def manage_risk(self, context: MarketContext) -> None:
        return

    def post_market(self, context: MarketContext) -> None:
        self.reset()

    def reset(self) -> None:
        self._position_open = False
        self.state_machine.reset()

    # ------------------------------------------------------------------
    def _within_entry_window(self, context: MarketContext) -> bool:
        now = context.timestamp.time()
        start = time.fromisoformat(self.configuration.entry_time)
        end = time.fromisoformat(self.configuration.no_new_entry_after)
        return start <= now < end
