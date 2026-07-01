"""
TradingBrain
Execution - Broker Interface

Order/Fill data structures plus the ``Broker`` interface every execution
backend (paper, MT5, Dhan, Zerodha) implements. Orders are expressed in
signed units (+ buy / - sell); fills come back priced and timestamped.

Author: TradingBrain
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from app.domains.execution.feed import MarketSnapshot
from app.domains.shared.enums import OptionRight


class OrderType(str, Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"


@dataclass(frozen=True, slots=True)
class Order:
    """An intent to trade one option/underlying instrument."""

    symbol: str
    instrument: str  # tradingsymbol
    quantity: int  # signed units (+ buy, - sell)
    order_type: OrderType = OrderType.MARKET
    limit_price: float | None = None
    right: OptionRight | None = None
    strike: float | None = None
    tag: str = ""

    @property
    def is_buy(self) -> bool:
        return self.quantity > 0


@dataclass(frozen=True, slots=True)
class Fill:
    """The result of executing an order."""

    order: Order
    quantity: int  # signed units actually filled
    price: float
    timestamp: datetime
    commission: float = 0.0
    metadata: dict[str, object] = field(default_factory=dict)

    @property
    def instrument(self) -> str:
        return self.order.instrument

    @property
    def symbol(self) -> str:
        return self.order.symbol


class Broker(ABC):
    """Abstract execution backend."""

    @abstractmethod
    def submit(self, order: Order, snapshot: MarketSnapshot) -> Fill | None:
        """
        Execute ``order`` against the current ``snapshot``.

        Returns a :class:`Fill`, or ``None`` if the order could not be
        filled (e.g. the instrument is absent from the chain).
        """
        raise NotImplementedError

    def submit_basket(
        self, orders: list[Order], snapshot: MarketSnapshot
    ) -> list[Fill]:
        """
        Execute a multi-leg basket. The caller orders the legs hedge-first
        (BUY protective legs before SELL writes) so the broker blocks only the
        reduced spread margin. The default implementation submits each leg in
        the given order; live brokers may override to place a true basket /
        preview combined margin first.
        """
        fills: list[Fill] = []
        for order in orders:
            fill = self.submit(order, snapshot)
            if fill is not None:
                fills.append(fill)
        return fills
