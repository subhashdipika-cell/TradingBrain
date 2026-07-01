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
        h, l, pc = candles[i].high, candles[i].low, candles[i - 1].close
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    return trs


def atr(candles: list, period: int = 14) -> float | None:
    trs = _true_ranges(candles)
    if len(trs) < period:
        return None
    return sum(trs[-period:]) / period


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
        h, l, pc = candles[i].high, candles[i].low, candles[i - 1].close
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))

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

    return Structure(ema_fast=ef, ema_slow=es, adx=a, atr=at, rsi=r,
                     trend=trend, vol_regime=vol)
