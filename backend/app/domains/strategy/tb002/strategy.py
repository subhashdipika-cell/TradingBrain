"""
TradingBrain

TB002 - ICT Liquidity Sweep Inversion Strategy
"""

from __future__ import annotations

from app.domains.strategy.contracts.context import MarketContext
from app.domains.strategy.contracts.signal import Signal
from app.domains.strategy.contracts.strategy import BaseStrategy
from app.domains.strategy.tb002.configuration import TB002Configuration
from app.domains.strategy.tb002.core_layer import CoreLayer
from app.domains.strategy.tb002.risk_layer import RiskLayer


class TB002Strategy(BaseStrategy):
    """
    TB002 - ICT Liquidity Sweep Inversion Strategy.

    Model summary:
    1. Higher-timeframe liquidity is swept.
    2. A higher-timeframe FVG is inverted.
    3. Price pulls back into a 15-minute PDA/FVG.
    4. A one-minute or five-minute inversion confirms entry.
    """

    name = "TB002"
    version = "1.0.0"
    description = "ICT Liquidity Sweep Inversion Strategy"

    def __init__(self, config: TB002Configuration | None = None) -> None:
        super().__init__()
        self.configuration = config or TB002Configuration()
        self.core_layer = CoreLayer(self.configuration)
        self.risk_layer = RiskLayer(self.configuration)

    def initialize(self) -> None:
        self.enabled = True
        self.state.initialized = True
        self.state.active = True

    def pre_market(self, context: MarketContext) -> None:
        return

    def generate_signal(self, context: MarketContext) -> Signal | None:
        if not self.enabled:
            return None

        signal = self.core_layer.evaluate(context)
        signal = self.risk_layer.validate(context, signal)
        if signal is not None:
            self.state.in_position = True
            self.state.entry_time = context.timestamp
            self.state.last_signal_time = context.timestamp
            self.state.trade_count += 1
        return signal

    def manage_position(self, context: MarketContext) -> Signal | None:
        if not self.enabled:
            return None
        signal = self.core_layer.manage_position(context)
        if signal is not None:
            self.state.in_position = False
            self.state.exit_time = context.timestamp
            self.state.last_signal_time = context.timestamp
        return signal

    def manage_risk(self, context: MarketContext) -> None:
        return

    def post_market(self, context: MarketContext) -> None:
        self.reset()

    def reset(self) -> None:
        self.core_layer.reset()
        self.state.in_position = False
        self.state.entry_time = None
        self.state.exit_time = None
