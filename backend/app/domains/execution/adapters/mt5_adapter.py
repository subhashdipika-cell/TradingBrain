"""
TradingBrain
Execution - MetaTrader 5 Adapter (live seam)

Implements the DataFeed/Broker interfaces against a MetaTrader5 terminal.

Status: SCAFFOLD. The ``MetaTrader5`` package is Windows-only and needs a
running terminal logged into a (demo or live) account. Because that cannot be
exercised in CI, the connection methods raise ``NotImplementedError`` with the
exact wiring required. Fill them in and test against an MT5 demo account.

Note: MT5 brokers typically offer FX/CFDs, not NSE index options - using this
adapter for NIFTY options requires a broker that actually lists them.
"""

from __future__ import annotations

from collections.abc import Iterator

from app.domains.execution.broker import Broker, Fill, Order
from app.domains.execution.feed import DataFeed, MarketSnapshot
from app.domains.market.symbol import InstrumentSpec


class MT5Feed(DataFeed):
    """Live market data from a MetaTrader5 terminal."""

    def __init__(self, *, spec: InstrumentSpec, login: int, server: str) -> None:
        self._spec = spec
        self._login = login
        self._server = server

    @property
    def spec(self) -> InstrumentSpec:
        return self._spec

    def connect(self, password: str) -> None:
        # TODO: import MetaTrader5 as mt5; mt5.initialize();
        # mt5.login(self._login, password, self._server)
        raise NotImplementedError(
            "MT5Feed.connect: initialize the MetaTrader5 terminal and login. "
            "Requires Windows + a running MT5 terminal and valid credentials."
        )

    def stream(self) -> Iterator[MarketSnapshot]:
        # TODO: poll mt5.symbol_info_tick / copy_rates_from_pos, build the
        # option chain (or map FX/CFD instruments) into MarketSnapshot.
        raise NotImplementedError("MT5Feed.stream: not yet implemented.")


class MT5Broker(Broker):
    """Live order execution via MetaTrader5."""

    def submit(self, order: Order, snapshot: MarketSnapshot) -> Fill | None:
        # TODO: build an mt5.order_send request from `order` and translate the
        # MT5 result into a Fill.
        raise NotImplementedError("MT5Broker.submit: not yet implemented.")
