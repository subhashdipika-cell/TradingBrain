"""
TradingBrain
Market - Option Chain

An option chain snapshot at a point in time. In a backtest the chain is
*synthesized* from spot + IV using the Black-Scholes engine; in live trading
the same structure is populated from a broker/exchange feed. Either way the
strategy and execution layers consume one stable interface.

Author: TradingBrain
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime

from app.domains.market.greeks import OptionGreeks, black_scholes
from app.domains.market.symbol import InstrumentSpec
from app.domains.shared.enums import OptionRight


@dataclass(frozen=True, slots=True)
class OptionQuote:
    """A single option contract quote with price and Greeks."""

    symbol: str
    expiry: date
    strike: float
    right: OptionRight
    greeks: OptionGreeks
    underlying: float

    @property
    def price(self) -> float:
        return self.greeks.price

    @property
    def tradingsymbol(self) -> str:
        return f"{self.symbol}{self.strike:.0f}{self.right.value[0]}E"


@dataclass(slots=True)
class OptionChain:
    """A strikes x rights grid for one underlying/expiry at one instant."""

    symbol: str
    underlying: float
    expiry: date
    timestamp: datetime
    quotes: dict[tuple[float, OptionRight], OptionQuote] = field(default_factory=dict)

    def add(self, quote: OptionQuote) -> None:
        self.quotes[(quote.strike, quote.right)] = quote

    def get(self, strike: float, right: OptionRight) -> OptionQuote | None:
        return self.quotes.get((strike, right))

    def strikes(self) -> list[float]:
        return sorted({strike for (strike, _right) in self.quotes})

    def atm_strike(self, step: float) -> float:
        return round(self.underlying / step) * step

    def nearest_strike(self, price: float | None = None) -> float | None:
        """
        Closest strike actually present in the chain to ``price`` (or the
        underlying). Robust to real chains that only quote strikes around ATM.
        Only strikes with *both* a call and a put are considered.
        """
        target = self.underlying if price is None else price
        complete = [
            s
            for s in self.strikes()
            if self.get(s, OptionRight.CALL) and self.get(s, OptionRight.PUT)
        ]
        if not complete:
            return None
        return min(complete, key=lambda s: abs(s - target))

    def straddle(self, strike: float) -> tuple[OptionQuote, OptionQuote] | None:
        """Return the (call, put) pair at ``strike`` if both exist."""
        call = self.get(strike, OptionRight.CALL)
        put = self.get(strike, OptionRight.PUT)
        if call is None or put is None:
            return None
        return call, put


def build_synthetic_chain(
    *,
    spec: InstrumentSpec,
    spot: float,
    expiry: date,
    timestamp: datetime,
    time_to_expiry: float,
    implied_vol: float,
    rate: float = 0.065,
    strikes_each_side: int = 10,
) -> OptionChain:
    """
    Build a Black-Scholes option chain around ``spot``.

    Generates ``strikes_each_side`` strikes above and below the ATM strike
    (at the instrument's strike step) and prices both calls and puts. Used by
    the backtest feed; live feeds populate :class:`OptionChain` directly.
    """
    chain = OptionChain(
        symbol=spec.symbol,
        underlying=spot,
        expiry=expiry,
        timestamp=timestamp,
    )

    atm = spec.atm_strike(spot)
    for i in range(-strikes_each_side, strikes_each_side + 1):
        strike = atm + i * spec.strike_step
        if strike <= 0:
            continue
        for right in (OptionRight.CALL, OptionRight.PUT):
            greeks = black_scholes(
                right=right,
                spot=spot,
                strike=strike,
                time_to_expiry=time_to_expiry,
                volatility=implied_vol,
                rate=rate,
            )
            chain.add(
                OptionQuote(
                    symbol=spec.symbol,
                    expiry=expiry,
                    strike=strike,
                    right=right,
                    greeks=greeks,
                    underlying=spot,
                )
            )

    return chain
