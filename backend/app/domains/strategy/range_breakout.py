"""
TradingBrain
Strategy - TB009 Range Breakout Credit (ITM directional credit spread)

Source: a systematic NSE options seller's positional leg (face-to-face
interview, Jul 2026). Mark the 09:15-11:15 IST range on the underlying; the
first CLOSE above the range high is bullish - sell an ITM PUT (hedged below);
the first close below the range low is bearish - sell an ITM CALL (hedged
above). Selling in-the-money puts the position's delta behind the breakout
while still collecting theta - a momentum trade expressed as a credit spread.

Deliberate adaptations for this platform (Stage 1):
- INTRADAY, squared off 15:15 like every other strategy here. His original
  carries overnight to ~09:35 next day (STBT); the engine's overnight-hold
  path is long-vol-only today, so the carry variant is deferred.
- His 0.5%-underlying stop is approximated by the engine's premium stop
  (stop_loss_pct=0.5): an ITM spread carries ~0.5-0.7 net delta, so a ~0.5%
  adverse NIFTY move grows the credit by roughly half.
- His "re-entry once after stop" maps to the engine's own convention: the
  engine resets the strategy after every closed position ("allow a fresh
  entry later in the session"), so a stopped breakout can re-enter if price
  breaks the range again - bounded by RiskLimits.max_trades_per_day and the
  daily-loss kill switch, not by a per-strategy counter.

The 09:15-11:15 range needs bars from BEFORE a live run starts (AutoTrader
begins ~10:20), so the range is read from ``metadata["day_candles_5m"]``
(full-day 5m history injected by the live ICT enricher) when present, else
from ``metadata["session_candles"]`` (the engine's rolling candle window -
complete in backtests, which start at the open). If neither covers the range
window adequately the strategy stands aside rather than trade a guessed range.

Directional evidence (AlphaEdge strategy-lab, ORB_2H_Breakout, ~14 sessions):
NIFTY 72.7% WR / net PF 1.69, SENSEX 63.6% / 1.54, BANKNIFTY 41.7% / 0.71 -
the breakout core works on NIFTY, which is what TradingBrain trades.

Author: TradingBrain
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, time

from app.domains.market.option_chain import OptionChain
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
class RangeBreakoutConfig:
    """Knobs for the TB009 range-breakout credit spread."""
    capital_allocation: float = 0.02   # max-loss budget (engine sizes to this)
    range_start: str = "09:15:00"
    range_end: str = "11:15:00"
    min_range_bars: int = 18           # ~20 of 24 5m bars: refuse a thin range
    short_itm_steps: int = 1           # strikes IN the money for the short leg
    wing_steps: int = 4                # strikes from short leg to the hedge
    target_profit_pct: float = 0.50
    stop_loss_pct: float = 0.50        # ~0.5% underlying move against (see module doc)
    square_off_time: str = "15:15:00"
    min_minutes_left: int = 45         # don't open a breakout too near square-off


class RangeBreakoutCreditStrategy(BaseStrategy):
    """TB009 - sell the ITM option in the breakout's direction, hedged."""

    name = "TB009"
    version = "1.0.0"
    description = "Range Breakout Credit - 09:15-11:15 range, sell ITM with hedge"
    structure = OptionStructure.BULL_PUT_SPREAD  # actual structure set per signal

    def __init__(self) -> None:
        super().__init__()
        self.configuration = RangeBreakoutConfig()
        self._last_entry_date: date | None = None
        self.enabled = True

    # ── lifecycle ─────────────────────────────────────────────────────────────
    def initialize(self) -> None:
        self.enabled = True

    def pre_market(self, context: MarketContext) -> None:
        return

    def manage_position(self, context: MarketContext) -> Signal | None:
        return None

    def manage_risk(self, context: MarketContext) -> None:
        return

    def post_market(self, context: MarketContext) -> None:
        self.reset()

    def reset(self) -> None:
        self._last_entry_date = None

    # ── range ─────────────────────────────────────────────────────────────────
    def _session_range(self, context: MarketContext) -> tuple[float, float] | None:
        """(high, low) of today's range window, or None when coverage is thin."""
        cfg = self.configuration
        start = time.fromisoformat(cfg.range_start)
        end = time.fromisoformat(cfg.range_end)
        today = context.timestamp.date()

        candles = context.metadata.get("day_candles_5m") or context.metadata.get(
            "session_candles"
        )
        if not candles:
            return None
        window = [
            c for c in candles
            if c.timestamp.date() == today and start <= c.timestamp.time() < end
        ]
        if len(window) < cfg.min_range_bars:
            return None
        return max(c.high for c in window), min(c.low for c in window)

    # ── signal ────────────────────────────────────────────────────────────────
    def generate_signal(self, context: MarketContext) -> Signal | None:
        if not self.enabled:
            return None
        chain: OptionChain | None = context.metadata.get("option_chain")
        if chain is None or not context.is_market_open:
            return None
        cfg = self.configuration
        now = context.timestamp.time()
        if now < time.fromisoformat(cfg.range_end):
            return None  # range still forming
        if context.minutes_to_close < cfg.min_minutes_left:
            return None
        day = context.timestamp.date()
        if self._last_entry_date == day:  # one entry per session
            return None

        rng = self._session_range(context)
        if rng is None:
            return None
        range_high, range_low = rng

        spot = context.last_price or chain.underlying
        if spot > range_high:
            bullish = True
        elif spot < range_low:
            bullish = False
        else:
            return None  # still inside the range

        complete = [
            s for s in chain.strikes()
            if chain.get(s, OptionRight.CALL) and chain.get(s, OptionRight.PUT)
        ]
        atm = chain.nearest_strike(spot)
        if atm is None or atm not in complete:
            return None
        idx = complete.index(atm)

        n, w = cfg.short_itm_steps, cfg.wing_steps
        if bullish:
            # Sell ITM put (strike above spot), hedge with a lower put.
            si, li = idx + n, idx + n - w
            right = OptionRight.PUT
            structure = OptionStructure.BULL_PUT_SPREAD
        else:
            # Sell ITM call (strike below spot), hedge with a higher call.
            si, li = idx - n, idx - n + w
            right = OptionRight.CALL
            structure = OptionStructure.BEAR_CALL_SPREAD
        if not (0 <= si < len(complete) and 0 <= li < len(complete)):
            return None
        short_strike, hedge_strike = complete[si], complete[li]

        short_q = chain.get(short_strike, right)
        hedge_q = chain.get(hedge_strike, right)
        if short_q is None or hedge_q is None:
            return None
        credit = short_q.price - hedge_q.price
        if credit <= 0:
            return None
        wing = abs(hedge_strike - short_strike)

        self._last_entry_date = day
        direction = "above" if bullish else "below"
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
            reason=(
                f"{structure.value}: spot {spot:.0f} broke {direction} "
                f"09:15-11:15 range [{range_low:.0f}, {range_high:.0f}]"
            ),
            metadata={
                "structure": structure.value,
                "body_strike": short_strike,
                "legs": [
                    {"right": right.value, "strike": hedge_strike, "side": "BUY"},
                    {"right": right.value, "strike": short_strike, "side": "SELL"},
                ],
                "entry_credit": credit,
                "wing_width": wing,
                "target_profit_pct": cfg.target_profit_pct,
                "stop_loss_pct": cfg.stop_loss_pct,
                "square_off_time": cfg.square_off_time,
                "range_high": range_high,
                "range_low": range_low,
            },
        )
