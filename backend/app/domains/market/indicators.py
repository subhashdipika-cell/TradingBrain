"""
TradingBrain
Market - Technical Indicators

Lightweight, dependency-free indicators used to read *market structure*
(trend / range / volatility) from a rolling candle window, so the regime
classifier and the strategy selector can route to the right option strategy.

Author: TradingBrain
"""

from __future__ import annotations

from dataclasses import dataclass

from app.domains.shared.enums import TrendDirection, VolatilityRegime


def ema(values: list[float], period: int) -> float | None:
    if len(values) < period:
        return None
    k = 2.0 / (period + 1)
    e = values[0]
    for v in values[1:]:
        e = v * k + e * (1 - k)
    return e


def rsi(closes: list[float], period: int = 14) -> float | None:
    if len(closes) < period + 1:
        return None
    gains = losses = 0.0
    for i in range(-period, 0):
        chg = closes[i] - closes[i - 1]
        gains += max(chg, 0.0)
        losses += max(-chg, 0.0)
    if losses == 0:
        return 100.0
    rs = (gains / period) / (losses / period)
    return 100.0 - 100.0 / (1.0 + rs)


def _true_ranges(candles: list) -> list[float]:
    trs = []
    for i in range(1, len(candles)):
        h, lo, pc = candles[i].high, candles[i].low, candles[i - 1].close
        trs.append(max(h - lo, abs(h - pc), abs(lo - pc)))
    return trs


def atr(candles: list, period: int = 14) -> float | None:
    trs = _true_ranges(candles)
    if len(trs) < period:
        return None
    return sum(trs[-period:]) / period


def _stddev(values: list[float]) -> float:
    n = len(values)
    if n == 0:
        return 0.0
    mean = sum(values) / n
    return (sum((v - mean) ** 2 for v in values) / n) ** 0.5


def bollinger(
    closes: list[float], period: int = 20, mult: float = 2.0
) -> tuple[float, float, float, float] | None:
    """Return ``(mid, upper, lower, bandwidth)`` for the last ``period`` closes.

    ``bandwidth`` is ``(upper - lower) / mid`` - a scale-free measure of how
    tight the bands are. A low bandwidth => a volatility *squeeze* (coiled).
    """
    if len(closes) < period:
        return None
    window = closes[-period:]
    mid = sum(window) / period
    sd = _stddev(window)
    upper = mid + mult * sd
    lower = mid - mult * sd
    bandwidth = (upper - lower) / mid if mid else 0.0
    return mid, upper, lower, bandwidth


def bollinger_squeeze(
    closes: list[float],
    period: int = 20,
    mult: float = 2.0,
    lookback: int = 20,
    pctile: float = 0.30,
) -> bool:
    """True when current band bandwidth sits in the bottom ``pctile`` of the
    last ``lookback`` readings - i.e. the tightest it has been recently (a
    classic Bollinger "squeeze": low volatility coiled for expansion).
    """
    if len(closes) < period + lookback:
        return False
    bws: list[float] = []
    for j in range(len(closes) - lookback, len(closes)):
        window = closes[j - period + 1 : j + 1]
        if len(window) < period:
            continue
        mid = sum(window) / period
        sd = _stddev(window)
        bws.append((2 * mult * sd) / mid if mid else 0.0)
    if len(bws) < 2:
        return False
    current = bws[-1]
    ranked = sorted(bws)
    threshold = ranked[max(0, int(pctile * len(ranked)) - 1)]
    return current <= threshold


def adx(candles: list, period: int = 14) -> float | None:
    """Wilder's ADX (simple-average variant) — trend strength 0..100."""
    if len(candles) < period * 2:
        return None
    plus_dm, minus_dm, trs = [], [], []
    for i in range(1, len(candles)):
        up = candles[i].high - candles[i - 1].high
        dn = candles[i - 1].low - candles[i].low
        plus_dm.append(up if (up > dn and up > 0) else 0.0)
        minus_dm.append(dn if (dn > up and dn > 0) else 0.0)
        h, lo, pc = candles[i].high, candles[i].low, candles[i - 1].close
        trs.append(max(h - lo, abs(h - pc), abs(lo - pc)))

    dxs = []
    for j in range(period, len(trs) + 1):
        tr = sum(trs[j - period:j]) or 1e-9
        pdi = 100 * sum(plus_dm[j - period:j]) / tr
        mdi = 100 * sum(minus_dm[j - period:j]) / tr
        denom = (pdi + mdi) or 1e-9
        dxs.append(100 * abs(pdi - mdi) / denom)
    if not dxs:
        return None
    return sum(dxs[-period:]) / min(period, len(dxs))


@dataclass(frozen=True, slots=True)
class Structure:
    """Indicator read of current market structure."""
    ema_fast: float
    ema_slow: float
    adx: float
    atr: float
    rsi: float
    trend: TrendDirection
    vol_regime: VolatilityRegime
    # Bollinger band read (drives the low-vol "coiled" convexity-buy setup, TB007)
    bb_mid: float = 0.0
    bb_upper: float = 0.0
    bb_lower: float = 0.0
    bb_bandwidth: float = 0.0
    squeeze: bool = False


def analyse(candles: list, *, fast: int = 9, slow: int = 21,
            iv: float = 0.0) -> Structure | None:
    """Compute structure from a candle window. Returns None until enough bars."""
    if len(candles) < slow + 2:
        return None
    closes = [c.close for c in candles]
    last = closes[-1]
    ef = ema(closes, fast) or last
    es = ema(closes, slow) or last
    a = adx(candles, 14) or 0.0
    at = atr(candles, 14) or 0.0
    r = rsi(closes, 14) or 50.0

    # Trend: EMA alignment + ADX strength. Needs a real trend (ADX) to call it.
    if a >= 20 and ef > es and last >= ef:
        trend = TrendDirection.BULLISH
    elif a >= 20 and ef < es and last <= ef:
        trend = TrendDirection.BEARISH
    else:
        trend = TrendDirection.SIDEWAYS

    # Volatility from ATR% of price (fallback for when IV isn't provided).
    atr_pct = (at / last * 100) if last else 0.0
    if iv and iv > 0:
        # implied vol given as a fraction (e.g. 0.14) — scale to annualised %.
        ivp = iv * 100 if iv < 3 else iv
        vol = (VolatilityRegime.EXTREME if ivp >= 30 else
               VolatilityRegime.HIGH if ivp >= 20 else
               VolatilityRegime.LOW if ivp < 10 else VolatilityRegime.NORMAL)
    else:
        vol = (VolatilityRegime.EXTREME if atr_pct >= 2.0 else
               VolatilityRegime.HIGH if atr_pct >= 1.2 else
               VolatilityRegime.LOW if atr_pct < 0.5 else VolatilityRegime.NORMAL)

    bb = bollinger(closes, period=20, mult=2.0)
    if bb is not None:
        bb_mid, bb_upper, bb_lower, bb_bandwidth = bb
    else:
        bb_mid = bb_upper = bb_lower = last
        bb_bandwidth = 0.0
    squeeze = bollinger_squeeze(closes, period=20, mult=2.0, lookback=20, pctile=0.30)

    return Structure(ema_fast=ef, ema_slow=es, adx=a, atr=at, rsi=r,
                     trend=trend, vol_regime=vol,
                     bb_mid=bb_mid, bb_upper=bb_upper, bb_lower=bb_lower,
                     bb_bandwidth=bb_bandwidth, squeeze=squeeze)
