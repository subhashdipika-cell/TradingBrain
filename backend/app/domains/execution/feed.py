"""
TradingBrain
Execution - Data Feed Interface

A ``DataFeed`` produces a stream of :class:`MarketSnapshot` objects - one per
bar. Each snapshot carries everything the engine needs to build a
``MarketContext`` and to price option legs: the underlying candle, the IV
estimate, the expiry, and a full option chain.

Backtest, paper and live feeds all implement this one interface, so the
engine is agnostic to where data comes from.

Author: TradingBrain
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date, datetime

from app.domains.market.candle import Candle
from app.domains.market.greeks import black_scholes
from app.domains.market.option_chain import OptionChain
from app.domains.market.symbol import InstrumentSpec
from app.domains.shared.enums import OptionRight


@dataclass(frozen=True, slots=True)
class MarketSnapshot:
    """Everything known about the market at one instant."""

    timestamp: datetime
    spec: InstrumentSpec
    candle: Candle
    implied_vol: float  # ATM implied vol (fraction)
    expiry: date
    time_to_expiry: float  # years
    option_chain: OptionChain
    vix: float = 0.0  # India VIX points (0 when unavailable -> use ATM IV proxy)
    # Optional NEXT-expiry chain, for calendar strategies (TB008). When present,
    # legs tagged ``far`` are priced against this chain / its time-to-expiry.
    far_chain: OptionChain | None = None
    far_expiry: date | None = None
    far_time_to_expiry: float = 0.0

    @property
    def symbol(self) -> str:
        return self.spec.symbol

    @property
    def spot(self) -> float:
        return self.candle.close

    def option_price(
        self, right: OptionRight, strike: float, *, far: bool = False
    ) -> float:
        """
        Price an option leg. Uses the live chain quote when present, else falls
        back to Black-Scholes - so legs whose strike is outside the chain window
        (a hedge wing) are still priced consistently for marking/exits/fills.

        ``far=True`` prices against the next-expiry chain (for calendar legs).
        """
        chain = self.far_chain if far else self.option_chain
        tte = self.far_time_to_expiry if far else self.time_to_expiry
        if chain is not None:
            quote = chain.get(strike, right)
            if quote is not None:
                return quote.price
        return black_scholes(
            right=right,
            spot=self.spot,
            strike=strike,
            time_to_expiry=max(tte, 1e-9),
            volatility=max(self.implied_vol, 1e-4),
        ).price


class DataFeed(ABC):
    """Abstract source of market snapshots."""

    @property
    @abstractmethod
    def spec(self) -> InstrumentSpec:
        """The instrument this feed serves."""
        raise NotImplementedError

    @abstractmethod
    def stream(self) -> Iterator[MarketSnapshot]:
        """Yield snapshots in chronological order."""
        raise NotImplementedError

    def __iter__(self) -> Iterator[MarketSnapshot]:
        return self.stream()
