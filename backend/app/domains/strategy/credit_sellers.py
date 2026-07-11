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

Strikes are chosen ``short_otm`` steps out of the money; hedges (condor/spreads)
``wing_otm`` steps beyond the short leg. All are option SELLING - net credit.

Author: TradingBrain
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from app.domains.market.option_chain import OptionChain
from app.domains.shared.enums import (
    OptionRight,
    OptionStructure,
    OrderSide,
    PositionSide,
    SignalType,
    TrendDirection,
)
from app.domains.strategy.contracts.context import MarketContext
from app.domains.strategy.contracts.signal import Signal
from app.domains.strategy.contracts.strategy import BaseStrategy


@dataclass(frozen=True, slots=True)
class CreditSellConfig:
    """Sizing / risk / strike knobs shared by the credit strategies.

    ``capital_allocation`` is the max-loss budget for hedged (defined-risk)
    structures — the engine sizes lots so total possible loss <= this fraction
    of capital (see engine._open_position). It must track the platform's
    per-position risk ceiling (RiskLimits.max_position_risk, 2%): a 2026-07-09
    TB006 Bear Call Spread realized only ~22% of its max loss yet still lost
    5.77% of the account in one trade, because this was set to 0.25 - a
    defined-risk spread could structurally lose up to a quarter of capital.
    The hedge leg itself was correctly sized; this was a risk-budget bug, not
    a missing hedge.
    """
    capital_allocation: float = 0.02       # fraction of capital risked / deployed
    max_daily_loss: float = 0.03
    max_strategy_drawdown: float = 0.10
    target_profit_pct: float = 0.50        # exit at 50% of the credit captured
    stop_loss_pct: float = 0.50            # stop when the credit grows 50%
    square_off_time: str = "15:15:00"
    short_otm: int = 2                     # strikes OTM for the short leg(s)
    wing_otm: int = 2                      # extra strikes OTM for the hedge leg(s)
    entry_after_min: int = 15              # wait this long after the open
    min_minutes_left: int = 30             # don't open too close to the square-off
    # Cost hurdle: skip entries whose credit is too small to clear round-trip
    # transaction costs. Real-data audit (Jul 2026, 15 Dhan sessions): TB004
    # banked Rs 2,659 gross but paid Rs 4,102 in costs (net -1,443) - the edge
    # was real, the tickets were too small. Credit is in premium points; the
    # banked target is ~ credit x target_pct x lot_size, so on NIFTY (lot 65)
    # a 4-leg condor needs roughly >= 12 pts to clear ~Rs 240/trade costs 2x.
    min_entry_credit: float = 0.0          # premium points; 0 = no hurdle
    # Trend gate: directional spreads must not fight the prevailing intraday
    # trend (TB005 sells puts - blocked in a BEARISH tape; TB006 sells calls -
    # blocked in a BULLISH tape). The AUTO router already routes by trend, but
    # isolated runs showed TB005 at PF 0.37 selling bull puts into declines.
    trend_gate: bool = True


def _price(chain: OptionChain, strike: float, right: OptionRight) -> float | None:
    q = chain.get(strike, right)
    return q.price if q is not None else None


def _oi_short_index(
    chain: OptionChain,
    complete: list[float],
    idx: int,
    *,
    direction: int,
    right: OptionRight,
    min_steps: int,
) -> int:
    """
    Index (into ``complete``) of the short leg for one side of a credit
    structure. Defaults to the fixed ``min_steps`` OTM offset (the original
    ATM-relative logic). When the chain carries usable OI, the short is
    pushed out to sit at/beyond the OI wall instead - max-Call-OI is
    resistance above spot, max-Put-OI is support below spot, and a seller is
    safer defended by a level the market has to break than by a fixed strike
    count. Never moves the short CLOSER to spot than ``min_steps``: that
    floor is a risk control, not a target, so a wall between spot and the
    floor is ignored rather than tightening the trade.
    """
    fallback = idx + direction * min_steps
    wall = chain.max_oi_strike(right)
    if wall is None:
        return fallback
    wall_strike, _wall_oi = wall
    if wall_strike not in complete:
        return fallback
    wall_idx = complete.index(wall_strike)
    return max(wall_idx, fallback) if direction > 0 else min(wall_idx, fallback)


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
        if cfg.trend_gate and not self._trend_ok(context):
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
        if credit < cfg.min_entry_credit:  # too small to clear costs
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
        self.reset()

    def reset(self) -> None:
        self._last_entry_date = None

    # ── hooks (subclasses) ────────────────────────────────────────────────────
    def _trend_ok(self, context: MarketContext) -> bool:
        """Directional-alignment veto. Default: any trend is fine (neutral
        structures). Directional spreads override to refuse fighting the tape."""
        return True

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
        # NOTE: naked SPAN margin on NIFTY is ~Rs 1.9L/lot; below ~Rs 7.5L
        # capital the engine sizes this to zero lots and it never trades
        # (confirmed on the Jul-2026 real-data audit). The AUTO router never
        # selects TB003 either - it exists for isolated runs at high capital.
        return CreditSellConfig(short_otm=3)

    def _legs(self, chain, complete, idx):
        n = self.configuration.short_otm
        ci = _oi_short_index(chain, complete, idx, direction=1, right=OptionRight.CALL, min_steps=n)
        pi = _oi_short_index(chain, complete, idx, direction=-1, right=OptionRight.PUT, min_steps=n)
        if ci >= len(complete) or pi < 0:
            return None
        sc, sp = complete[ci], complete[pi]
        cp, pp = _price(chain, sc, OptionRight.CALL), _price(chain, sp, OptionRight.PUT)
        if cp is None or pp is None:
            return None
        legs = [
            {"right": "CALL", "strike": sc, "side": "SELL"},
            {"right": "PUT", "strike": sp, "side": "SELL"},
        ]
        return OptionStructure.SHORT_STRANGLE, legs, cp + pp, None


# ── TB004 · Iron Condor (defined risk) ────────────────────────────────────────
class IronCondorStrategy(CreditSellStrategy):
    name = "TB004"
    version = "1.1.0"
    description = "Iron Condor - defined-risk OTM strangle (range)"
    structure = OptionStructure.IRON_CONDOR

    def _make_config(self) -> CreditSellConfig:
        # min_entry_credit=8: real-data sweep (15 sessions) cut the cost bleed
        # from -1,443 to -1,040 by refusing sub-8-pt condors whose banked decay
        # can't clear 8 fills of friction. 4 legs x 2 sides ~ Rs 240+/trade.
        return CreditSellConfig(min_entry_credit=8.0)

    def _legs(self, chain, complete, idx):
        n, w = self.configuration.short_otm, self.configuration.wing_otm
        ci = _oi_short_index(chain, complete, idx, direction=1, right=OptionRight.CALL, min_steps=n)
        pi = _oi_short_index(chain, complete, idx, direction=-1, right=OptionRight.PUT, min_steps=n)
        lci, lpi = ci + w, pi - w
        if ci >= len(complete) or pi < 0 or lci >= len(complete) or lpi < 0:
            return None
        sc, sp, lc, lp = complete[ci], complete[pi], complete[lci], complete[lpi]
        scp = _price(chain, sc, OptionRight.CALL)
        spp = _price(chain, sp, OptionRight.PUT)
        lcp = _price(chain, lc, OptionRight.CALL)
        lpp = _price(chain, lp, OptionRight.PUT)
        if None in (scp, spp, lcp, lpp):
            return None
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
    version = "1.1.0"
    description = "Bull Put Spread - sell OTM put + buy lower put (bullish)"
    structure = OptionStructure.BULL_PUT_SPREAD

    def _make_config(self) -> CreditSellConfig:
        # Gate + min_entry_credit=8: real-data sweep took TB005 from PF 0.37
        # (-5,259, losing pre-cost) to PF 0.67 (-1,561, gross positive). Still
        # the weakest book; standalone use is discouraged - AUTO only routes
        # it on bullish structure.
        return CreditSellConfig(min_entry_credit=8.0)

    def _trend_ok(self, context: MarketContext) -> bool:
        # Selling puts into a falling tape was the audit's worst edge
        # (PF 0.37, -Rs 5,259): require the trend NOT be bearish.
        return context.trend is not TrendDirection.BEARISH

    def _legs(self, chain, complete, idx):
        n, w = self.configuration.short_otm, self.configuration.wing_otm
        si = _oi_short_index(chain, complete, idx, direction=-1, right=OptionRight.PUT, min_steps=n)
        li = si - w
        if si < 0 or li < 0:
            return None
        ss, ls = complete[si], complete[li]
        ssp, lsp = _price(chain, ss, OptionRight.PUT), _price(chain, ls, OptionRight.PUT)
        if ssp is None or lsp is None:
            return None
        legs = [
            {"right": "PUT", "strike": ls, "side": "BUY"},    # hedge (lower)
            {"right": "PUT", "strike": ss, "side": "SELL"},   # write
        ]
        return OptionStructure.BULL_PUT_SPREAD, legs, ssp - lsp, ss - ls


# ── TB006 · Bear Call Spread (bearish credit) ─────────────────────────────────
class BearCallSpreadStrategy(CreditSellStrategy):
    name = "TB006"
    version = "1.1.0"
    description = "Bear Call Spread - sell OTM call + buy higher call (bearish)"
    structure = OptionStructure.BEAR_CALL_SPREAD

    def _make_config(self) -> CreditSellConfig:
        # min_entry_credit=4. Honest note: on the 15-session real-data sample
        # the trend gate REDUCED PF (1.19 -> 1.07); it is kept anyway as tail
        # protection - selling calls into a rising tape is the exact shape of
        # the 2026-07-09 kill-switch loss, and 15 sessions is not evidence to
        # optimize away a structural safety rule.
        return CreditSellConfig(min_entry_credit=4.0)

    def _trend_ok(self, context: MarketContext) -> bool:
        # Mirror of TB005: don't sell calls into a rising tape.
        return context.trend is not TrendDirection.BULLISH

    def _legs(self, chain, complete, idx):
        n, w = self.configuration.short_otm, self.configuration.wing_otm
        si = _oi_short_index(chain, complete, idx, direction=1, right=OptionRight.CALL, min_steps=n)
        li = si + w
        if si >= len(complete) or li >= len(complete):
            return None
        ss, ls = complete[si], complete[li]
        ssp, lsp = _price(chain, ss, OptionRight.CALL), _price(chain, ls, OptionRight.CALL)
        if ssp is None or lsp is None:
            return None
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
