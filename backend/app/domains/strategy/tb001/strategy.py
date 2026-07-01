"""
TradingBrain

TB001 - Dynamic Theta Harvesting Strategy
"""

from __future__ import annotations

from app.domains.strategy.contracts.context import MarketContext
from app.domains.strategy.contracts.signal import Signal
from app.domains.strategy.contracts.strategy import BaseStrategy

from app.domains.strategy.tb001.configuration import TB001Configuration
from app.domains.strategy.tb001.core_layer import CoreLayer
from app.domains.strategy.tb001.greeks import GreeksService
from app.domains.strategy.tb001.position_manager import PositionManager
from app.domains.strategy.tb001.regime import RegimeDetector
from app.domains.strategy.tb001.risk_layer import RiskLayer
from app.domains.strategy.tb001.state_machine import StateMachine
from app.domains.strategy.tb001.tactical_layer import TacticalLayer


class TB001Strategy(BaseStrategy):
    """
    TB001 - Dynamic Theta Harvesting Strategy.
    """

    name = "TB001"
    version = "1.0.0"
    description = "Dynamic Theta Harvesting Strategy"

    def __init__(self) -> None:
        super().__init__()

        self.configuration = TB001Configuration()

        self.state_machine = StateMachine()

        self.regime_detector = RegimeDetector()

        self.greeks = GreeksService()

        self.core_layer = CoreLayer(
            self.configuration,
        )

        self.tactical_layer = TacticalLayer(
            self.configuration,
        )

        self.position_manager = PositionManager(
            self.configuration,
        )

        self.risk_layer = RiskLayer(
            self.configuration,
        )

    def initialize(self) -> None:
        self.enabled = True

    def pre_market(
        self,
        context: MarketContext,
    ) -> None:
        """
        Reserved for future implementation.
        """
        return

    def generate_signal(
        self,
        context: MarketContext,
    ) -> Signal | None:
        """
        Execute TB001 workflow.
        """

        # Detect market regime.
        context.market_regime = (
            self.regime_detector.detect(context)
        )

        # Read Greeks.
        _ = self.greeks.get_snapshot(context)

        # Core Strategy
        signal = self.core_layer.evaluate(context)

        # Tactical Layer
        signal = self.tactical_layer.evaluate(
            context,
            signal,
        )

        # Position Management
        signal = self.position_manager.manage(
            context,
            signal,
        )

        # Strategy Risk Validation
        signal = self.risk_layer.validate(
            context,
            signal,
        )

        return signal

    def manage_position(
        self,
        context: MarketContext,
    ) -> Signal | None:
        return None

    def manage_risk(
        self,
        context: MarketContext,
    ) -> None:
        return

    def post_market(
        self,
        context: MarketContext,
    ) -> None:
        self.reset()

    def reset(self) -> None:
        self.core_layer.reset()
        self.state_machine.reset()