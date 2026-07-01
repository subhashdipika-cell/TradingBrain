"""
TradingBrain
Execution - Zerodha (Kite Connect) Adapter (live seam)

Implements the DataFeed/Broker interfaces against Zerodha's Kite Connect API.
Kite offers NSE F&O including index options.

Status: SCAFFOLD. Requires a Kite api_key + access_token (refreshed daily via
the login flow). Calls raise ``NotImplementedError`` until implemented and
tested against a live Kite account.
"""

from __future__ import annotations

from collections.abc import Iterator

from app.domains.execution.broker import Broker, Fill, Order
from app.domains.execution.feed import DataFeed, MarketSnapshot
from app.domains.market.symbol import InstrumentSpec


class ZerodhaFeed(DataFeed):
    """Live NSE option-chain feed via Kite Connect."""

    def __init__(
        self, *, spec: InstrumentSpec, api_key: str, access_token: str
    ) -> None:
        self._spec = spec
        self._api_key = api_key
        self._access_token = access_token

    @property
    def spec(self) -> InstrumentSpec:
        return self._spec

    def stream(self) -> Iterator[MarketSnapshot]:
        # TODO: use KiteTicker WebSocket; assemble option chain from instrument
        # tokens and quotes into MarketSnapshot.
        raise NotImplementedError(
            "ZerodhaFeed.stream: implement Kite ticker subscription. "
            "Requires KITE_API_KEY and a daily KITE_ACCESS_TOKEN."
        )


class ZerodhaBroker(Broker):
    """Live order execution via Kite Connect."""

    def __init__(self, *, api_key: str, access_token: str) -> None:
        self._api_key = api_key
        self._access_token = access_token

    def submit(self, order: Order, snapshot: MarketSnapshot) -> Fill | None:
        # TODO: kite.place_order(...), poll order book, translate to Fill.
        raise NotImplementedError("ZerodhaBroker.submit: not yet implemented.")
