"""
TradingBrain

TB002 - ICT Primitives

Pure, dependency-light detectors for the building blocks of the ICT
liquidity-sweep inversion model, operating on lists of :class:`Candle`:

- Fair Value Gaps (FVG)         - 3-candle price imbalances.
- Inversion FVGs (IFVG)         - an FVG that price violates and rejects from.
- Swing highs / lows            - local extremes = resting liquidity pools.
- Liquidity sweeps              - price runs a swing level then closes back.

These are the vocabulary the :class:`ICTDetector` assembles into a full setup.

Author: TradingBrain
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from app.domains.market.candle import Candle


@dataclass(frozen=True, slots=True)
class FVG:
    """A fair value gap (3-candle imbalance)."""

    direction: str  # "BULLISH" or "BEARISH"
    index: int  # index of the middle candle of the 3-candle pattern
    low: float  # lower bound of the gap
    high: float  # upper bound of the gap
    inverted: bool = False
    inverted_index: int | None = None  # bar index where the gap was violated

    @property
    def candles_to_invert(self) -> int | None:
        if self.inverted_index is None:
            return None
        return self.inverted_index - self.index

    def contains(self, price: float) -> bool:
        return self.low <= price <= self.high


@dataclass(frozen=True, slots=True)
class Sweep:
    """A liquidity sweep of a swing level."""

    side: str  # "BUY_SIDE" (swept a high) or "SELL_SIDE" (swept a low)
    level_index: int
    sweep_index: int
    reference_price: float  # the swing level that was run
    swept_price: float  # the extreme the sweep reached


# ---------------------------------------------------------------------
# Fair value gaps
# ---------------------------------------------------------------------
def find_fvgs(candles: list[Candle]) -> list[FVG]:
    """Return every 3-candle fair value gap in ``candles``."""
    gaps: list[FVG] = []
    for i in range(1, len(candles) - 1):
        prev, nxt = candles[i - 1], candles[i + 1]
        if prev.high < nxt.low:  # bullish imbalance (gap up)
            gaps.append(FVG("BULLISH", i, prev.high, nxt.low))
        elif prev.low > nxt.high:  # bearish imbalance (gap down)
            gaps.append(FVG("BEARISH", i, nxt.high, prev.low))
    return gaps


def mark_inversions(candles: list[Candle], gaps: list[FVG]) -> list[FVG]:
    """
    Flag gaps that price later *inverts*: a bullish FVG inverts when a candle
    closes below its low (support becomes resistance); a bearish FVG inverts
    when a candle closes above its high.
    """
    out: list[FVG] = []
    for gap in gaps:
        inverted_index: int | None = None
        for j in range(gap.index + 2, len(candles)):
            close = candles[j].close
            if gap.direction == "BULLISH" and close < gap.low:
                inverted_index = j
                break
            if gap.direction == "BEARISH" and close > gap.high:
                inverted_index = j
                break
        out.append(
            replace(
                gap, inverted=inverted_index is not None, inverted_index=inverted_index
            )
        )
    return out


def fair_value_gaps(candles: list[Candle]) -> list[FVG]:
    """Convenience: all FVGs with inversion state resolved."""
    return mark_inversions(candles, find_fvgs(candles))


# ---------------------------------------------------------------------
# Swing structure / liquidity
# ---------------------------------------------------------------------
def swing_high_indices(
    candles: list[Candle], left: int = 2, right: int = 2
) -> list[int]:
    """Indices of swing highs (local maxima) = buy-side liquidity."""
    out: list[int] = []
    for i in range(left, len(candles) - right):
        h = candles[i].high
        if all(h > candles[i - k].high for k in range(1, left + 1)) and all(
            h >= candles[i + k].high for k in range(1, right + 1)
        ):
            out.append(i)
    return out


def swing_low_indices(
    candles: list[Candle], left: int = 2, right: int = 2
) -> list[int]:
    """Indices of swing lows (local minima) = sell-side liquidity."""
    out: list[int] = []
    for i in range(left, len(candles) - right):
        low = candles[i].low
        if all(low < candles[i - k].low for k in range(1, left + 1)) and all(
            low <= candles[i + k].low for k in range(1, right + 1)
        ):
            out.append(i)
    return out


# ---------------------------------------------------------------------
# Sweeps
# ---------------------------------------------------------------------
def detect_sweep_of_high(candles: list[Candle], level_index: int) -> Sweep | None:
    """A later candle whose high exceeds the swing high but closes back below."""
    level = candles[level_index].high
    for j in range(level_index + 1, len(candles)):
        c = candles[j]
        if c.high > level and c.close < level:
            return Sweep(
                side="BUY_SIDE",
                level_index=level_index,
                sweep_index=j,
                reference_price=level,
                swept_price=c.high,
            )
    return None


def detect_sweep_of_low(candles: list[Candle], level_index: int) -> Sweep | None:
    """A later candle whose low breaks the swing low but closes back above."""
    level = candles[level_index].low
    for j in range(level_index + 1, len(candles)):
        c = candles[j]
        if c.low < level and c.close > level:
            return Sweep(
                side="SELL_SIDE",
                level_index=level_index,
                sweep_index=j,
                reference_price=level,
                swept_price=c.low,
            )
    return None


def latest_sweep(candles: list[Candle], left: int = 2, right: int = 2) -> Sweep | None:
    """
    The most recent liquidity sweep (of a swing high or low). Returns the one
    with the largest sweep index (closest to 'now').
    """
    candidates: list[Sweep] = []
    for idx in swing_high_indices(candles, left, right):
        sweep = detect_sweep_of_high(candles, idx)
        if sweep is not None:
            candidates.append(sweep)
    for idx in swing_low_indices(candles, left, right):
        sweep = detect_sweep_of_low(candles, idx)
        if sweep is not None:
            candidates.append(sweep)
    if not candidates:
        return None
    return max(candidates, key=lambda s: s.sweep_index)
