"""
TradingBrain
Execution - Paper Broker

Simulated execution used for backtests and paper trading. Option orders are
filled at the current chain price adjusted for slippage, with a simple
commission model. This is the default :class:`Broker` until a live adapter
is wired in.

Author: TradingBrain
"""

from __future__ import annotations

from app.domains.execution.broker import Broker, Fill, Order
from app.domains.execution.costs import CostModel, IndianOptionsCostModel
from app.domains.execution.feed import MarketSnapshot
from app.domains.shared.utils import round_to_tick


class PaperBroker(Broker):
    """
    Fills orders against the snapshot's option chain with slippage and a
    realistic transaction-cost model (NSE options by default), so backtest
    PnL reflects net-of-cost results.
    """

    def __init__(
        self,
        *,
        slippage_pct: float = 0.0,
        cost_model: CostModel | None = None,
        tick_size: float = 0.05,
    ) -> None:
        self._slippage_pct = slippage_pct
        self._cost_model = cost_model or IndianOptionsCostModel()
        self._tick_size = tick_size

    def submit(self, order: Order, snapshot: MarketSnapshot) -> Fill | None:
        price = self._reference_price(order, snapshot)
        if price is None:
            return None

        fill_price = self._apply_slippage(price, order.is_buy)
        fill_price = round_to_tick(fill_price, self._tick_size)
        fill_price = max(fill_price, 0.0)

        breakdown = self._cost_model.charge(
            price=fill_price,
            units=abs(order.quantity),
            is_buy=order.is_buy,
        )

        return Fill(
            order=order,
            quantity=order.quantity,
            price=fill_price,
            timestamp=snapshot.timestamp,
            commission=breakdown.total,
            metadata={"cost_breakdown": breakdown},
        )

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _reference_price(self, order: Order, snapshot: MarketSnapshot) -> float | None:
        if order.strike is not None and order.right is not None:
            quote = snapshot.option_chain.get(order.strike, order.right)
            return None if quote is None else quote.price
        # Non-option instrument: fill at the underlying close.
        return snapshot.spot

    def _apply_slippage(self, price: float, is_buy: bool) -> float:
        if self._slippage_pct <= 0.0:
            return price
        adjustment = price * self._slippage_pct
        return price + adjustment if is_buy else price - adjustment
