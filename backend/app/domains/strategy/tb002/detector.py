"""
TradingBrain

TB002 - ICT Setup Detector

Assembles the four ICT layers from multi-timeframe candles into the
``tb002_setup`` metadata dict that TB002 consumes:

    HTF liquidity sweep  ->  HTF inversion FVG  ->  15m pullback FVG (tapped)
    ->  LTF (1m/5m) inversion trigger

and derives the trade geometry (entry / stop above the swept high / target at
the opposing draw on liquidity) with a risk:reward check. Returns ``None`` when
a complete, valid setup is not present - which, faithfully, is most of the time.

Author: TradingBrain
"""

from __future__ import annotations

from datetime import datetime

from app.domains.market.candle import Candle
from app.domains.strategy.tb002.ict_primitives import (
    FVG,
    Sweep,
    detect_sweep_of_high,
    detect_sweep_of_low,
    fair_value_gaps,
    swing_high_indices,
    swing_low_indices,
)


class ICTDetector:
    """Detects a complete TB002 ICT setup from multi-timeframe candles."""

    def __init__(
        self,
        *,
        swing_left: int = 2,
        swing_right: int = 2,
        max_htf_inversion_candles: int = 2,
        min_risk_reward: float = 1.5,
        stop_buffer_frac: float = 0.0005,
    ) -> None:
        self._left = swing_left
        self._right = swing_right
        self._max_inv = max_htf_inversion_candles
        self._min_rr = min_risk_reward
        self._buf = stop_buffer_frac

    # ------------------------------------------------------------------
    def detect(
        self,
        *,
        htf: list[Candle],
        m15: list[Candle],
        ltf: list[Candle],
        now: datetime,
        ltf_timeframe: str = "5m",
    ) -> dict | None:
        """Return a ``tb002_setup`` dict, or ``None`` if no valid setup."""
        if len(htf) < 5 or len(m15) < 5 or len(ltf) < 5:
            return None
        for direction in ("BEARISH", "BULLISH"):
            setup = self._detect(direction, htf, m15, ltf, now, ltf_timeframe)
            if setup is not None:
                return setup
        return None

    # ------------------------------------------------------------------
    def _detect(
        self,
        direction: str,
        htf: list[Candle],
        m15: list[Candle],
        ltf: list[Candle],
        now: datetime,
        ltf_timeframe: str,
    ) -> dict | None:
        bearish = direction == "BEARISH"

        # 1) HTF liquidity sweep of the side matching the direction (bearish
        # needs a swept HIGH = buy-side; bullish a swept LOW = sell-side).
        sweep = self._directional_sweep(htf, bearish)
        if sweep is None:
            return None

        # 2) HTF inversion FVG after the sweep (the displacement leg).
        htf_inv = self._htf_inversion(htf, sweep, bearish)
        if htf_inv is None:
            return None

        # 3) 15m pullback FVG in the trade direction, tapped by price.
        pullback = self._pullback(m15, bearish, htf_inv)
        if pullback is None:
            return None

        # 4) LTF inversion trigger (change in state of delivery).
        trigger = self._ltf_trigger(ltf, bearish)
        if trigger is None:
            return None

        # 5) Geometry: entry / stop / targets + risk:reward.
        geo = self._geometry(direction, htf, m15, ltf)
        if geo is None:
            return None
        entry, stop, first_target, external_target = geo

        return {
            "direction": direction,
            "entry_price": entry,
            "stop_loss": stop,
            "first_target": first_target,
            "external_target": external_target,
            "sweep": {
                "side": sweep.side,
                "timeframe": "1h",
                "reference_price": sweep.reference_price,
                "swept_price": sweep.swept_price,
                "confirmed": True,
            },
            "htf_inversion": {
                "direction": direction,
                "timeframe": "1h",
                "low": htf_inv.low,
                "high": htf_inv.high,
                "inverted": True,
                "candles_to_invert": htf_inv.candles_to_invert,
            },
            "pullback_gap": {
                "direction": direction,
                "timeframe": "15m",
                "low": pullback.low,
                "high": pullback.high,
                "tapped": True,
                "inside_parent": self._inside(pullback, htf_inv),
            },
            "trigger": {
                "direction": direction,
                "timeframe": ltf_timeframe,
                "price": ltf[-1].close,
                "low": trigger.low,
                "high": trigger.high,
                "confirmed": True,
            },
            "setup_time": now.isoformat(),
            "notes": [f"{direction} ICT sweep+IFVG+15m pullback+LTF trigger"],
        }

    # ------------------------------------------------------------------
    # Layer detectors
    # ------------------------------------------------------------------
    def _directional_sweep(self, htf: list[Candle], bearish: bool) -> Sweep | None:
        candidates: list[Sweep] = []
        if bearish:
            for idx in swing_high_indices(htf, self._left, self._right):
                sweep = detect_sweep_of_high(htf, idx)
                if sweep is not None:
                    candidates.append(sweep)
        else:
            for idx in swing_low_indices(htf, self._left, self._right):
                sweep = detect_sweep_of_low(htf, idx)
                if sweep is not None:
                    candidates.append(sweep)
        if not candidates:
            return None
        return max(candidates, key=lambda s: s.sweep_index)

    def _htf_inversion(
        self, htf: list[Candle], sweep: Sweep, bearish: bool
    ) -> FVG | None:
        # Bearish setup: a bullish FVG that inverts (price closes below it);
        # bullish setup: a bearish FVG that inverts (closes above it).
        want = "BULLISH" if bearish else "BEARISH"
        best: FVG | None = None
        for gap in fair_value_gaps(htf):
            if gap.direction != want or not gap.inverted:
                continue
            if gap.inverted_index is None or gap.inverted_index < sweep.sweep_index:
                continue
            if (gap.candles_to_invert or 999) > self._max_inv:
                continue
            if best is None or gap.inverted_index > (best.inverted_index or -1):
                best = gap
        return best

    def _pullback(self, m15: list[Candle], bearish: bool, htf_inv: FVG) -> FVG | None:
        want = "BEARISH" if bearish else "BULLISH"
        best: FVG | None = None
        for gap in fair_value_gaps(m15):
            if gap.direction != want:
                continue
            if not self._tapped(m15, gap, bearish):
                continue
            if best is None or gap.index > best.index:
                best = gap
        return best

    def _ltf_trigger(self, ltf: list[Candle], bearish: bool) -> FVG | None:
        # Opposite-direction FVG that inverts = change in state of delivery.
        want = "BULLISH" if bearish else "BEARISH"
        best: FVG | None = None
        for gap in fair_value_gaps(ltf):
            if gap.direction != want or not gap.inverted:
                continue
            if best is None or (gap.inverted_index or -1) > (best.inverted_index or -1):
                best = gap
        return best

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _tapped(candles: list[Candle], gap: FVG, bearish: bool) -> bool:
        after = candles[gap.index + 2 :]
        if bearish:
            # price retraces UP into a bearish gap
            return any(c.high >= gap.low for c in after)
        # price retraces DOWN into a bullish gap
        return any(c.low <= gap.high for c in after)

    @staticmethod
    def _inside(child: FVG, parent: FVG) -> bool:
        return child.low >= parent.low and child.high <= parent.high

    def _geometry(
        self,
        direction: str,
        htf: list[Candle],
        m15: list[Candle],
        ltf: list[Candle],
    ) -> tuple[float, float, float, float] | None:
        entry = ltf[-1].close
        bearish = direction == "BEARISH"

        highs = [m15[i].high for i in swing_high_indices(m15, self._left, self._right)]
        lows = [m15[i].low for i in swing_low_indices(m15, self._left, self._right)]
        highs += [htf[i].high for i in swing_high_indices(htf, self._left, self._right)]
        lows += [htf[i].low for i in swing_low_indices(htf, self._left, self._right)]

        if bearish:
            stops = [h for h in highs if h > entry]
            if not stops:
                return None
            stop = min(stops) * (1.0 + self._buf)  # just above nearest swing high
            risk = stop - entry
            if risk <= 0:
                return None
            lows_below = [low for low in lows if low < entry]
            # The *first* target must itself be >= min_rr away (TB002 validates
            # initial_target's R:R); the external target is the farthest draw.
            qualifying = [
                low for low in lows_below if (entry - low) >= self._min_rr * risk
            ]
            if not qualifying:
                return None
            first_target = max(qualifying)  # nearest draw still >= min R:R
            external_target = min(lows_below)  # farthest draw (runner)
        else:
            stops = [low for low in lows if low < entry]
            if not stops:
                return None
            stop = max(stops) * (1.0 - self._buf)  # just below nearest swing low
            risk = entry - stop
            if risk <= 0:
                return None
            highs_above = [h for h in highs if h > entry]
            qualifying = [h for h in highs_above if (h - entry) >= self._min_rr * risk]
            if not qualifying:
                return None
            first_target = min(qualifying)
            external_target = max(highs_above)

        return entry, stop, first_target, external_target
