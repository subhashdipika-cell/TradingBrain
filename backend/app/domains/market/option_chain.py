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
    open_interest: float = 0.0
    volume: float = 0.0

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

    # ── Open interest (OI) ──────────────────────────────────────────────────
    # Sellers care where OI concentrates: the exchange's biggest open call/put
    # positions mark levels the market has historically had to work to break
    # (walls), and where they cluster brackets the strike option writers as a
    # whole lose the least at expiry (max pain) - both are levels a short
    # strike is safer parked at/beyond, not just N strikes OTM of spot.

    def has_oi_data(self) -> bool:
        """False for chains with no OI (e.g. the synthetic backtest chain) -
        callers should fall back to plain ATM-offset strike selection."""
        return any(q.open_interest > 0 for q in self.quotes.values())

    def max_oi_strike(self, right: OptionRight) -> tuple[float, float] | None:
        """(strike, OI) with the highest open interest for one side, or
        ``None`` when this chain carries no usable OI for that side."""
        best: tuple[float, float] | None = None
        for strike in self.strikes():
            quote = self.get(strike, right)
            if quote is None:
                continue
            if best is None or quote.open_interest > best[1]:
                best = (strike, quote.open_interest)
        if best is None or best[1] <= 0:
            return None
        return best

    def put_call_oi_ratio(self) -> float | None:
        """Total put OI / total call OI, or ``None`` when call OI is 0."""
        call_oi = sum(
            q.open_interest for (_s, r), q in self.quotes.items() if r == OptionRight.CALL
        )
        put_oi = sum(
            q.open_interest for (_s, r), q in self.quotes.items() if r == OptionRight.PUT
        )
        if call_oi <= 0:
            return None
        return put_oi / call_oi

    def max_pain_strike(self) -> float | None:
        """The strike at which option writers' aggregate expiry payout across
        the whole chain is smallest - classic "max pain". ``None`` when the
        chain has no strikes or no OI to weight the calculation with."""
        strikes = self.strikes()
        if not strikes or not self.has_oi_data():
            return None
        best_strike: float | None = None
        best_loss: float | None = None
        for candidate in strikes:
            loss = 0.0
            for strike in strikes:
                call = self.get(strike, OptionRight.CALL)
                if call is not None and candidate > strike:
                    loss += (candidate - strike) * call.open_interest
                put = self.get(strike, OptionRight.PUT)
                if put is not None and candidate < strike:
                    loss += (strike - candidate) * put.open_interest
            if best_loss is None or loss < best_loss:
                best_loss, best_strike = loss, candidate
        return best_strike


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
