"""
TradingBrain
Strategy - Option-Selling (Credit) Strategies

A family of premium-selling strategies that plug into the generic engine by
emitting ``metadata.legs`` (the engine sizes, hedges and manages them). Each is
selected by market structure:

    TB003 Short Strangle   - naked OTM strangle (range, collect premium)
    TB004 Iron Condor      - defined-risk OTM strangle (range, capped tail)
    TB005 Bull Put Spread  - sell OTM put + buy lower put (bullish credit)
    TB006 Bear Call Spread - sell OTM call + buy higher call (bearish credit)

    Strikes are selected by target delta; hedges are selected farther OTM by a
    lower target delta. All are option SELLING - net credit.

Author: TradingBrain
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from app.domains.market.option_chain import OptionChain, OptionQuote
from app.domains.shared.enums import (
    OptionRight,
    OptionStructure,
    OrderSide,
    PositionSide,
    SignalType,
)
from app.domains.strategy.contracts.context import MarketContext
from app.domains.strategy.contracts.signal import Signal
from app.domains.strategy.contracts.strategy import BaseStrategy


@dataclass(frozen=True, slots=True)
class CreditSellConfig:
    """Sizing / risk / strike knobs shared by the credit strategies."""
    capital_allocation: float = 0.25       # fraction of capital risked / deployed
    max_daily_loss: float = 0.03
    max_strategy_drawdown: float = 0.10
    target_profit_pct: float = 0.50        # exit at 50% of the credit captured
    stop_loss_pct: float = 0.50            # stop when the credit grows 50%
    square_off_time: str = "15:15:00"
    short_delta: float = 0.18              # target absolute delta for shorts
    hedge_delta: float = 0.08              # target absolute delta for hedges
    # Require enough premium relative to the defined loss width. Very low
    # credit/width trades have poor reward-to-risk after costs and are more
    # sensitive to small mark-to-market moves.
    min_credit_to_width: float = 0.25
    max_spread_pct: float = 0.08
    min_open_interest: float = 100_000.0
    min_volume: float = 1_000.0
    entry_after_min: int = 30              # avoid opening auction noise
    min_minutes_left: int = 30             # don't open too close to the square-off


def _select_delta(
    chain: OptionChain,
    right: OptionRight,
    target_delta: float,
    *,
    direction: str | None = None,
    reference_strike: float | None = None,
) -> OptionQuote | None:
    """Select the closest valid delta, optionally on one side of a short."""
    candidates = []
    for (strike, quote_right), quote in chain.quotes.items():
        if quote_right is not right or quote.price <= 0:
            continue
        if (
            direction == "higher"
            and reference_strike is not None
            and strike <= reference_strike
        ):
            continue
        if (
            direction == "lower"
            and reference_strike is not None
            and strike >= reference_strike
        ):
            continue
        candidates.append(quote)
    if not candidates:
        return None
    return min(candidates, key=lambda q: abs(abs(q.greeks.delta) - target_delta))


class CreditSellStrategy(BaseStrategy):
    """Base for premium-selling strategies. Subclasses build the legs."""

    structure = OptionStructure.SHORT_STRANGLE

    def __init__(self) -> None:
        super().__init__()
        self.configuration = self._make_config()
        self._last_entry_date: date | None = None
        self.enabled = True

    def _make_config(self) -> CreditSellConfig:
        return CreditSellConfig()

    # ── lifecycle ─────────────────────────────────────────────────────────────
    def initialize(self) -> None:
        self.enabled = True
        self._last_entry_date = None

    def pre_market(self, context: MarketContext) -> None:
        return

    def generate_signal(self, context: MarketContext) -> Signal | None:
        if not self.enabled:
            return None
        chain: OptionChain | None = context.metadata.get("option_chain")
        if chain is None or not context.is_market_open:
            return None
        cfg = self.configuration
        if context.minutes_from_open < cfg.entry_after_min:
            return None
        if context.minutes_to_close < cfg.min_minutes_left:
            return None
        day = context.timestamp.date()
        if self._last_entry_date == day:   # one entry per session
            return None

        spot = context.last_price or chain.underlying
        atm = chain.nearest_strike(spot)
        if atm is None:
            return None
        complete = [
            s for s in chain.strikes()
            if chain.get(s, OptionRight.CALL) and chain.get(s, OptionRight.PUT)
        ]
        if atm not in complete:
            return None
        idx = complete.index(atm)

        plan = self._legs(chain, complete, idx)
        if plan is None:
            return None
        structure, legs, credit, wing = plan
        if credit <= 0:
            return None

        strict_liquidity = bool(context.metadata.get("live_chain"))
        for leg in legs:
            quote = chain.get(float(leg["strike"]), OptionRight(leg["right"]))
            if quote is None:
                return None
            liquid, reason = quote.liquidity_check(
                now=context.timestamp,
                max_spread_pct=cfg.max_spread_pct,
                min_open_interest=cfg.min_open_interest,
                min_volume=cfg.min_volume,
                require_microstructure=strict_liquidity,
            )
            if not liquid:
                context.metadata["entry_rejection"] = f"liquidity: {reason}"
                return None

        if wing is not None and credit / wing < cfg.min_credit_to_width:
            context.metadata["entry_rejection"] = "credit-to-width below threshold"
            return None

        self._last_entry_date = day
        return Signal(
            strategy=self.name,
            symbol=context.symbol,
            signal_type=SignalType.SELL,
            side=OrderSide.SELL,
            position_side=PositionSide.SHORT,
            entry_price=spot,
            requested_risk=cfg.capital_allocation,
            confidence=0.6,
            score=credit,
            reason=f"{structure.value} @ ATM {atm:.0f} (credit {credit:.2f})",
            metadata={
                "structure": structure.value,
                "body_strike": atm,
                "legs": legs,
                "entry_credit": credit,
                "wing_width": wing,        # None => naked (SPAN-margin sized)
                "target_profit_pct": cfg.target_profit_pct,
                "stop_loss_pct": cfg.stop_loss_pct,
                "square_off_time": cfg.square_off_time,
            },
        )

    def manage_position(self, context: MarketContext) -> Signal | None:
        return None

    def manage_risk(self, context: MarketContext) -> None:
        return

    def post_market(self, context: MarketContext) -> None:
        # A new entry is permitted only after the next session starts. The
        # engine calls reset() after every exit; clearing the date there would
        # allow repeated same-day re-entry after a stop-loss, turning one bad
        # regime into a sequence of losses.
        self._last_entry_date = None

    def reset(self) -> None:
        return

    # ── leg construction (subclasses) ─────────────────────────────────────────
    def _legs(self, chain: OptionChain, complete: list[float], idx: int):
        """Return (structure, legs, entry_credit, wing_width) or None."""
        raise NotImplementedError


# ── TB003 · Short Strangle (naked) ────────────────────────────────────────────
class ShortStrangleStrategy(CreditSellStrategy):
    name = "TB003"
    version = "1.0.0"
    description = "Short Strangle - naked OTM premium selling (range)"
    structure = OptionStructure.SHORT_STRANGLE

    def _make_config(self) -> CreditSellConfig:
        return CreditSellConfig(short_delta=0.18)

    def _legs(self, chain, complete, idx):
        scq = _select_delta(chain, OptionRight.CALL, self.configuration.short_delta)
        spq = _select_delta(chain, OptionRight.PUT, self.configuration.short_delta)
        if scq is None or spq is None:
            return None
        sc, sp = scq.strike, spq.strike
        cp, pp = scq.price, spq.price
        legs = [
            {"right": "CALL", "strike": sc, "side": "SELL"},
            {"right": "PUT", "strike": sp, "side": "SELL"},
        ]
        return OptionStructure.SHORT_STRANGLE, legs, cp + pp, None


# ── TB004 · Iron Condor (defined risk) ────────────────────────────────────────
class IronCondorStrategy(CreditSellStrategy):
    name = "TB004"
    version = "1.0.0"
    description = "Iron Condor - defined-risk OTM strangle (range)"
    structure = OptionStructure.IRON_CONDOR

    def _legs(self, chain, complete, idx):
        scq = _select_delta(chain, OptionRight.CALL, self.configuration.short_delta)
        spq = _select_delta(chain, OptionRight.PUT, self.configuration.short_delta)
        if scq is None or spq is None:
            return None
        lcq = _select_delta(
            chain,
            OptionRight.CALL,
            self.configuration.hedge_delta,
            direction="higher",
            reference_strike=scq.strike,
        )
        lpq = _select_delta(
            chain,
            OptionRight.PUT,
            self.configuration.hedge_delta,
            direction="lower",
            reference_strike=spq.strike,
        )
        if lcq is None or lpq is None:
            return None
        sc, sp, lc, lp = scq.strike, spq.strike, lcq.strike, lpq.strike
        scp, spp, lcp, lpp = scq.price, spq.price, lcq.price, lpq.price
        credit = (scp + spp) - (lcp + lpp)
        wing = max(lc - sc, sp - lp)
        legs = [
            {"right": "CALL", "strike": lc, "side": "BUY"},   # hedge
            {"right": "PUT", "strike": lp, "side": "BUY"},    # hedge
            {"right": "CALL", "strike": sc, "side": "SELL"},  # write
            {"right": "PUT", "strike": sp, "side": "SELL"},   # write
        ]
        return OptionStructure.IRON_CONDOR, legs, credit, wing


# ── TB005 · Bull Put Spread (bullish credit) ──────────────────────────────────
class BullPutSpreadStrategy(CreditSellStrategy):
    name = "TB005"
    version = "1.0.0"
    description = "Bull Put Spread - sell OTM put + buy lower put (bullish)"
    structure = OptionStructure.BULL_PUT_SPREAD

    def _legs(self, chain, complete, idx):
        ssq = _select_delta(chain, OptionRight.PUT, self.configuration.short_delta)
        if ssq is None:
            return None
        lsq = _select_delta(
            chain,
            OptionRight.PUT,
            self.configuration.hedge_delta,
            direction="lower",
            reference_strike=ssq.strike,
        )
        if lsq is None:
            return None
        ss, ls = ssq.strike, lsq.strike
        ssp, lsp = ssq.price, lsq.price
        legs = [
            {"right": "PUT", "strike": ls, "side": "BUY"},    # hedge (lower)
            {"right": "PUT", "strike": ss, "side": "SELL"},   # write
        ]
        return OptionStructure.BULL_PUT_SPREAD, legs, ssp - lsp, ss - ls


# ── TB006 · Bear Call Spread (bearish credit) ─────────────────────────────────
class BearCallSpreadStrategy(CreditSellStrategy):
    name = "TB006"
    version = "1.0.0"
    description = "Bear Call Spread - sell OTM call + buy higher call (bearish)"
    structure = OptionStructure.BEAR_CALL_SPREAD

    def _legs(self, chain, complete, idx):
        ssq = _select_delta(chain, OptionRight.CALL, self.configuration.short_delta)
        if ssq is None:
            return None
        lsq = _select_delta(
            chain,
            OptionRight.CALL,
            self.configuration.hedge_delta,
            direction="higher",
            reference_strike=ssq.strike,
        )
        if lsq is None:
            return None
        ss, ls = ssq.strike, lsq.strike
        ssp, lsp = ssq.price, lsq.price
        legs = [
            {"right": "CALL", "strike": ls, "side": "BUY"},   # hedge (higher)
            {"right": "CALL", "strike": ss, "side": "SELL"},  # write
        ]
        return OptionStructure.BEAR_CALL_SPREAD, legs, ssp - lsp, ls - ss


CREDIT_STRATEGIES = [
    ShortStrangleStrategy,
    IronCondorStrategy,
    BullPutSpreadStrategy,
    BearCallSpreadStrategy,
]
