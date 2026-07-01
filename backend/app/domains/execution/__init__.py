"""
TradingBrain
Execution Domain

Data feeds and brokers behind stable interfaces so the same engine can run a
backtest, a paper session, or live trading by swapping the adapter.
"""

from app.domains.execution.broker import Broker, Fill, Order, OrderType
from app.domains.execution.costs import (
    CostBreakdown,
    CostModel,
    CostRates,
    FlatCostModel,
    IndianOptionsCostModel,
)
from app.domains.execution.feed import DataFeed, MarketSnapshot
from app.domains.execution.paper_broker import PaperBroker

__all__ = [
    "Broker",
    "CostBreakdown",
    "CostModel",
    "CostRates",
    "DataFeed",
    "Fill",
    "FlatCostModel",
    "IndianOptionsCostModel",
    "MarketSnapshot",
    "Order",
    "OrderType",
    "PaperBroker",
]
