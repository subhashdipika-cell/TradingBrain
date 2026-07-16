"""
TradingBrain
Market - Level Engine (context awareness / "human touch")

Fixes the three mechanical flaws of emotion-free directional trading:

    1. Chasing        - entering after the move already happened
    2. No map         - longing into resistance / shorting into support
    3. Blind targets  - a target placed beyond the barrier price must break

Builds a level map before a directional entry: fractal swing highs/lows +
previous-day high/low (from the engine's rolling candle window) + round
numbers + the option chain's OI walls (max call-OI strike = resistance,
max put-OI strike = support, straight off MarketContext). Then checks:

    freshness        : (close - ema_fast) / ATR must be <= ext_max_atr
                       in the trade direction
    location         : no entry within loc_atr * ATR of the opposing wall
    R:R to structure : (room to the wall - buffer) / stop distance >= min_rr

and CAPS the take-profit just before the wall, never beyond it.

Applies only to signals carrying underlying geometry (entry/stop/target) -
credit structures (iron fly / strangle / calendar / straddle) are direction-
neutral and pass through untouched.

Config: backend/level_config.json (optional).
    {"enforce": false} -> shadow mode: violations only journaled, nothing blocked.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from app.domains.market.candle import Candle
from app.domains.strategy.contracts.context import MarketContext
from app.domains.strategy.contracts.signal import Signal
from app.domains.shared.enums import PositionSide

CONFIG_FILE = Path(__file__).resolve().parents[3] / "level_config.json"

DEFAULTS = {
    "enforce": True,            # False = shadow (journal only, never block)
    "min_rr_structure": 1.2,
    "buffer_atr": 0.25,
    "loc_atr": 0.35,
    "ext_max_atr": 1.5,
    "min_barrier_strength": 1.0,
}

# Round-number gravity (minor step, major step) - majors are walls.
ROUND_STEPS = {
    "NIFTY": (100, 500),
    "NIFTY50": (100, 500),
    "BANKNIFTY": (500, 1000),
    "SENSEX": (500, 1000),
    "FINNIFTY": (100, 500),
}


def get_config() -> dict:
    cfg = dict(DEFAULTS)
    try:
        cfg.update(json.loads(CONFIG_FILE.read_text(encoding="utf-8")))
    except Exception:
        pass
    return cfg


@dataclass(slots=True)
class LevelCheck:
    """Outcome of the human-touch checks for one directional signal."""

    ok: bool = True                      # False -> skip the entry (enforce mode)
    violations: list[str] = field(default_factory=list)
    rr_structure: float | None = None
    extension: float | None = None
    barrier: float | None = None
    barrier_kind: str = ""
    capped_target: float | None = None   # set when the TP was pulled inside the wall
    note: str = ""


def _swings(candles: list[Candle], lb: int = 3) -> tuple[list[float], list[float]]:
    highs = [c.high for c in candles]
    lows = [c.low for c in candles]
    sh, sl = [], []
    # Exclude the forming bar so a breakout isn't walled by itself.
    for i in range(lb, len(candles) - 1 - lb):
        if all(highs[i] > highs[j] for j in range(i - lb, i + lb + 1) if j != i):
            sh.append(highs[i])
        if all(lows[i] < lows[j] for j in range(i - lb, i + lb + 1) if j != i):
            sl.append(lows[i])
    return sh[-8:], sl[-8:]


def _prev_day(candles: list[Candle]) -> tuple[float | None, float | None]:
    days = sorted({c.timestamp.date() for c in candles})
    if len(days) < 2:
        return None, None
    prev = days[-2]
    bars = [c for c in candles if c.timestamp.date() == prev]
    return max(c.high for c in bars), min(c.low for c in bars)


def build_level_map(
    candles: list[Candle], context: MarketContext, symbol: str
) -> list[dict]:
    """Clustered level list: [{price, kind, strength}], sorted by price."""
    spot = context.last_price or context.close_price
    if not spot or len(candles) < 30:
        return []
    raw: list[dict] = []

    sh, sl = _swings(candles)
    raw += [{"price": p, "kind": "swing-high", "strength": 1.0} for p in sh]
    raw += [{"price": p, "kind": "swing-low", "strength": 1.0} for p in sl]

    pdh, pdl = _prev_day(candles)
    if pdh:
        raw.append({"price": pdh, "kind": "pdh", "strength": 1.3})
    if pdl:
        raw.append({"price": pdl, "kind": "pdl", "strength": 1.3})

    step, major = ROUND_STEPS.get(symbol.upper(), (100, 500))
    base = round(spot / step) * step
    for k in range(-3, 4):
        p = base + k * step
        if p > 0:
            raw.append({"price": float(p), "kind": "round",
                        "strength": 1.2 if p % major == 0 else 0.6})

    # OI walls straight off the enriched context (chain already analysed).
    if context.max_call_oi_strike:
        raw.append({"price": float(context.max_call_oi_strike),
                    "kind": "ce-wall", "strength": 1.6})
    if context.max_put_oi_strike:
        raw.append({"price": float(context.max_put_oi_strike),
                    "kind": "pe-wall", "strength": 1.6})

    tol = spot * 0.001
    raw.sort(key=lambda l: l["price"])
    levels: list[dict] = []
    for l in raw:
        if levels and abs(l["price"] - levels[-1]["price"]) <= tol:
            levels[-1]["strength"] = round(levels[-1]["strength"] + l["strength"], 2)
            if l["kind"] not in levels[-1]["kind"]:
                levels[-1]["kind"] += "+" + l["kind"]
        else:
            levels.append(dict(l))
    return levels


def check_signal(
    signal: Signal,
    context: MarketContext,
    candles: list[Candle],
    cfg: dict | None = None,
) -> LevelCheck:
    """Run the human-touch checks. Only gates directional signals with
    underlying geometry; multi-leg credit/volatility structures pass through."""
    cfg = cfg or get_config()
    out = LevelCheck()

    meta = signal.metadata or {}
    structural = any(
        isinstance(meta.get(k), list) and meta[k]
        for k in ("legs", "straddle_legs", "calendar_legs")
    )
    if structural or not signal.stop_loss or not signal.entry_price:
        out.note = "non-directional structure - level checks not applicable"
        return out

    atr = context.atr or 0.0
    spot = context.last_price or context.close_price
    if atr <= 0 or not spot:
        out.note = "no ATR/spot - level checks skipped"
        return out

    entry = float(signal.entry_price)
    risk = abs(entry - float(signal.stop_loss))
    long = signal.position_side is PositionSide.LONG
    buffer = cfg["buffer_atr"] * atr

    # 1) Freshness - extension beyond the fast EMA in the trade direction.
    if context.ema_fast:
        ext = (spot - context.ema_fast) / atr
        dir_ext = ext if long else -ext
        out.extension = round(dir_ext, 2)
        if dir_ext > cfg["ext_max_atr"]:
            out.violations.append(
                f"Chasing - price {dir_ext:.1f}xATR beyond the fast EMA; "
                "the move already happened"
            )

    levels = build_level_map(candles, context, signal.symbol)
    strong = [l for l in levels if l["strength"] >= cfg["min_barrier_strength"]]
    eps = spot * 0.0002
    if long:
        opp = [l for l in strong if l["price"] > entry + eps]
        barrier = min(opp, key=lambda l: l["price"]) if opp else None
    else:
        opp = [l for l in strong if l["price"] < entry - eps]
        barrier = max(opp, key=lambda l: l["price"]) if opp else None

    if barrier:
        out.barrier = barrier["price"]
        out.barrier_kind = barrier["kind"]
        dist = abs(barrier["price"] - entry)
        # 2) Location.
        if dist <= cfg["loc_atr"] * atr:
            out.violations.append(
                f"{'Longing into resistance' if long else 'Shorting into support'}"
                f" @ {barrier['price']:g} ({barrier['kind']}) only {dist:.0f} pts away"
            )
        # 3) R:R to structure.
        if risk > 0:
            out.rr_structure = round(max(0.0, dist - buffer) / risk, 2)
            if out.rr_structure < cfg["min_rr_structure"]:
                out.violations.append(
                    f"Only {out.rr_structure}R of room to {barrier['price']:g}"
                    f" ({barrier['kind']}) - target would sit beyond structure"
                )
        # 4) Barrier-aware target cap.
        if signal.take_profit:
            tp = float(signal.take_profit)
            capped = barrier["price"] - buffer if long else barrier["price"] + buffer
            tighter = (long and capped < tp) or (not long and capped > tp)
            beyond_entry = capped > entry if long else capped < entry
            if tighter and beyond_entry:
                out.capped_target = round(capped, 2)

    out.ok = not (cfg["enforce"] and out.violations)
    return out
