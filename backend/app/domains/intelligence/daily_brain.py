"""
TradingBrain
Intelligence - The Daily Brain

The meta-layer the app is named after. Once per trading day, BEFORE entries:

  1. CONFIRM the regime from the last 2-3 days of actual market behaviour
     (NIFTY 5-minute bars + India VIX via Dhan) — drift, day-direction
     consistency, path efficiency (trendiness), ranges, overnight gaps.
     A per-bar classifier reacts to the last candle; the brain looks at how
     the market has been BEHAVING, which is what regime actually means.

  2. PICK today's strategy with a learning rule, not a fixed map: a UCB
     (upper-confidence-bound) bandit per regime, seeded with the structure
     router's priors, updated with every realized forward-test outcome.
     Strategies that keep paying in a regime get picked more; ones that
     bleed get benched — automatically, from evidence. If nothing has a
     positive expectancy in this regime, the brain says STAND_ASIDE:
     knowing when not to trade is also a decision.

  3. LEARN: every forward-test result is recorded against the day's regime
     (`record_outcome`), so the memory (brain_memory.json) converges on the
     regime->strategy truth for THIS market, not a backtest's.

  4. READ THE VAULT: the Obsidian trades folder holds machine-readable
     monthly exports from all four trading apps; the brain surfaces their
     realized stats in its daily plan as cross-app evidence.

Author: TradingBrain
"""

from __future__ import annotations

import json
import math
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.core.config import settings

IST = timezone(timedelta(hours=5, minutes=30))

MEMORY_FILE = Path(__file__).resolve().parents[2] / "data" / "brain_memory.json"

NIFTY_ID, VIX_ID = 13, 21          # Dhan IDX_I security ids
LOOKBACK_DAYS = 3                  # trading days of behaviour to confirm regime

# Exploration constant for UCB (day returns are in % of capital, typically ±1-3).
UCB_C = 0.8

STAND_ASIDE = "STAND_ASIDE"

# Priors seed the bandit so day one isn't random — they encode the structure
# router's mapping (confirmed with the user) as pseudo-observations of
# `PRIOR_N` days each. Real outcomes overwhelm them quickly.
PRIOR_N = 2
PRIORS: dict[str, dict[str, float]] = {
    "TREND_UP":      {"TB005": 0.50, "TB002": 0.30, "TB004": 0.10},
    "TREND_DOWN":    {"TB006": 0.50, "TB002": 0.30, "TB004": 0.10},
    "RANGE_QUIET":   {"TB001": 0.50, "TB008": 0.40, "TB004": 0.20},
    "RANGE_ACTIVE":  {"TB004": 0.50, "TB001": 0.15, "TB005": 0.10, "TB006": 0.10},
    "VOLATILE_CHOP": {"TB004": 0.10, "TB002": 0.05},
}
POOL = ["TB001", "TB002", "TB004", "TB005", "TB006", "TB008"]


# ── memory ───────────────────────────────────────────────────────────────────

def _load_memory() -> dict:
    try:
        return json.loads(MEMORY_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {"regimes": {}, "plans": {}}


def _save_memory(mem: dict) -> None:
    MEMORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    mem["updated"] = datetime.now(IST).isoformat(timespec="seconds")
    MEMORY_FILE.write_text(json.dumps(mem, indent=2), encoding="utf-8")


# ── market lookback ──────────────────────────────────────────────────────────

def _dhan():
    from dhanhq import DhanContext, dhanhq
    from app.application.forward_test import _load_credentials
    client_id, token = _load_credentials()
    return dhanhq(DhanContext(client_id, token))


def _intraday_days(dhan, security_id: int, days_back: int = 8) -> dict[str, list[dict]]:
    """5-minute bars grouped by IST date, oldest->newest within each day."""
    to_d = datetime.now(IST).strftime("%Y-%m-%d")
    from_d = (datetime.now(IST) - timedelta(days=days_back)).strftime("%Y-%m-%d")
    resp = dhan.intraday_minute_data(
        security_id=str(security_id), exchange_segment="IDX_I",
        instrument_type="INDEX", from_date=from_d, to_date=to_d, interval=5)
    data = resp.get("data", resp) if isinstance(resp, dict) else {}
    if isinstance(data, dict) and isinstance(data.get("data"), dict):
        data = data["data"]
    o, h, l, c, t = (data.get(k) or [] for k in ("open", "high", "low", "close", "timestamp"))
    by_day: dict[str, list[dict]] = {}
    for i in range(min(len(o), len(c), len(t))):
        day = datetime.fromtimestamp(float(t[i]), tz=timezone.utc).astimezone(IST).strftime("%Y-%m-%d")
        by_day.setdefault(day, []).append(
            {"o": float(o[i]), "h": float(h[i]), "l": float(l[i]), "c": float(c[i])})
    return by_day


def _lookback_features() -> dict:
    """Behaviour features over the last LOOKBACK_DAYS completed trading days."""
    dhan = _dhan()
    today = datetime.now(IST).strftime("%Y-%m-%d")
    nifty = _intraday_days(dhan, NIFTY_ID)
    days = sorted(d for d in nifty if d < today)[-LOOKBACK_DAYS:]
    if not days:
        raise RuntimeError("No NIFTY lookback data from Dhan.")

    per_day = []
    for d in days:
        bars = nifty[d]
        o, c = bars[0]["o"], bars[-1]["c"]
        hi, lo = max(b["h"] for b in bars), min(b["l"] for b in bars)
        path = sum(abs(bars[i]["c"] - bars[i - 1]["c"]) for i in range(1, len(bars)))
        per_day.append({"date": d, "open": o, "close": c,
                        "drift_pct": round((c - o) / o * 100, 3),
                        "range_pct": round((hi - lo) / o * 100, 3),
                        "path_pct": round(path / o * 100, 3)})

    first_o, last_c = per_day[0]["open"], per_day[-1]["close"]
    net_drift = (last_c - first_o) / first_o * 100
    total_path = sum(d["path_pct"] for d in per_day) or 1e-9
    efficiency = abs(net_drift) / total_path                     # 0=chop, →1=clean trend
    signs = [1 if d["drift_pct"] > 0 else -1 for d in per_day]
    consistency = abs(sum(signs)) / len(signs)                    # 1 = every day same way
    avg_range = sum(d["range_pct"] for d in per_day) / len(per_day)
    gaps = [abs(per_day[i]["open"] - per_day[i - 1]["close"]) / per_day[i - 1]["close"] * 100
            for i in range(1, len(per_day))]
    max_gap = max(gaps) if gaps else 0.0

    vix = None
    try:
        vdays = _intraday_days(dhan, VIX_ID)
        vd = sorted(d for d in vdays if d < today)
        if vd:
            vix = round(vdays[vd[-1]][-1]["c"], 2)
    except Exception:
        pass

    return {"days": per_day, "net_drift_pct": round(net_drift, 3),
            "efficiency": round(efficiency, 3), "consistency": round(consistency, 2),
            "avg_day_range_pct": round(avg_range, 3), "max_gap_pct": round(max_gap, 3),
            "vix": vix}


def _classify(f: dict) -> tuple[str, str]:
    """Daily-scale regime from multi-day behaviour. Returns (label, reason)."""
    vix = f.get("vix")
    quiet_vol = (vix is not None and vix < 14) or (vix is None and f["avg_day_range_pct"] < 0.7)

    # Trend: meaningful multi-day drift, a majority of days pointing the same
    # way (consistency 0.3 = 2-of-3), and price moving efficiently, not churning.
    if f["efficiency"] >= 0.12 and abs(f["net_drift_pct"]) >= 0.8 and f["consistency"] >= 0.3:
        label = "TREND_UP" if f["net_drift_pct"] > 0 else "TREND_DOWN"
        reason = (f"net drift {f['net_drift_pct']:+.2f}% over {len(f['days'])} days with "
                  f"{int(f['consistency']*100)}% day-direction consistency and efficiency "
                  f"{f['efficiency']:.2f} — a real trend, not noise.")
    # Chop needs genuinely wide behaviour — big ranges, big gaps, or fear in
    # VIX. (A single 0.8% weekend gap on a VIX-12 tape is NOT chop.)
    elif f["avg_day_range_pct"] >= 1.3 or f["max_gap_pct"] >= 1.2 or (vix is not None and vix >= 18):
        label = "VOLATILE_CHOP"
        reason = (f"big daily ranges (avg {f['avg_day_range_pct']:.2f}%), max gap "
                  f"{f['max_gap_pct']:.2f}%, VIX {vix} — wide and directionless.")
    elif quiet_vol:
        label = "RANGE_QUIET"
        reason = (f"low drift ({f['net_drift_pct']:+.2f}%), calm ranges "
                  f"(avg {f['avg_day_range_pct']:.2f}%), VIX {vix} — theta-friendly.")
    else:
        label = "RANGE_ACTIVE"
        reason = (f"no directional edge (drift {f['net_drift_pct']:+.2f}%, efficiency "
                  f"{f['efficiency']:.2f}) but normal-vol ranges — defined-risk territory.")
    return label, reason


# ── the bandit ───────────────────────────────────────────────────────────────

def _arm_stats(mem: dict, regime: str) -> dict[str, dict]:
    """Merged prior+learned stats per strategy for a regime."""
    learned = (mem.get("regimes") or {}).get(regime, {})
    stats = {}
    for s in POOL:
        prior_mean = PRIORS.get(regime, {}).get(s, 0.0)
        ln, lmean = 0, 0.0
        if s in learned:
            ln, lmean = int(learned[s].get("n", 0)), float(learned[s].get("mean", 0.0))
        n = PRIOR_N + ln
        mean = (PRIOR_N * prior_mean + ln * lmean) / n
        stats[s] = {"n": n, "mean": round(mean, 4), "learned_n": ln,
                    "learned_mean": round(lmean, 4), "prior": prior_mean}
    return stats


def _pick(stats: dict[str, dict]) -> tuple[str, dict[str, float]]:
    total = sum(v["n"] for v in stats.values())
    scores = {s: v["mean"] + UCB_C * math.sqrt(math.log(total + 1) / v["n"])
              for s, v in stats.items()}
    best = max(scores, key=scores.get)
    # If even the optimistic score of the best arm is negative, don't trade:
    # every strategy is losing in this regime on the evidence we have.
    if scores[best] < 0:
        return STAND_ASIDE, {k: round(v, 4) for k, v in scores.items()}
    return best, {k: round(v, 4) for k, v in scores.items()}


# ── vault evidence (Obsidian cross-app learning input) ───────────────────────

def vault_evidence() -> list[dict]:
    """Realized stats from every app's latest monthly export in the vault.
    The exports carry YAML frontmatter, so the vault is machine-readable —
    the four apps' broker-realized truth in one place."""
    root = Path(settings.OBSIDIAN_TRADES_DIR)
    out = []
    if not root.exists():
        return out
    keys = ("win_rate", "mt5_win_rate", "mt5_net_usd", "net_r", "trades",
            "mt5_trades", "net", "wins", "losses")
    for app_dir in sorted(p for p in root.iterdir() if p.is_dir()):
        months = sorted(app_dir.glob("2*.md"))
        if not months:
            continue
        try:
            text = months[-1].read_text(encoding="utf-8", errors="replace")
            m = re.match(r"^---\n(.*?)\n---", text, re.S)
            if not m:
                continue
            stats = {}
            for line in m.group(1).splitlines():
                if ":" not in line:
                    continue
                k, v = line.split(":", 1)
                if k.strip() in keys and v.strip():
                    stats[k.strip()] = v.strip()
            if stats:
                out.append({"app": app_dir.name, "file": months[-1].name, **stats})
        except Exception:
            continue
    return out


# ── public API ───────────────────────────────────────────────────────────────

def plan(force: bool = False) -> dict:
    """Today's brain plan (cached per IST date): confirmed regime, evidence,
    chosen strategy (or STAND_ASIDE), and the full scoring for transparency."""
    today = datetime.now(IST).strftime("%Y-%m-%d")
    mem = _load_memory()
    if not force and today in (mem.get("plans") or {}):
        return mem["plans"][today]

    from app.domains.market.holidays import trading_day_check
    ok_day, why = trading_day_check()

    features = _lookback_features()
    regime, reason = _classify(features)
    stats = _arm_stats(mem, regime)
    choice, scores = _pick(stats)
    if not ok_day:
        choice = STAND_ASIDE
        reason = f"{why} {reason}"

    p = {
        "date": today, "trading_day": ok_day,
        "regime": regime, "reason": reason,
        "strategy": choice,
        "lookback": features,
        "arm_stats": stats, "ucb_scores": scores,
        "vault_evidence": vault_evidence(),
        "generated": datetime.now(IST).isoformat(timespec="seconds"),
    }
    mem.setdefault("plans", {})[today] = p
    _save_memory(mem)
    return p


def record_outcome(strategy: str, net_return_pct: float, date: str | None = None) -> dict:
    """Feed a realized day result back into the bandit memory. The regime is
    taken from that day's stored plan (or classified fresh if absent)."""
    day = date or datetime.now(IST).strftime("%Y-%m-%d")
    mem = _load_memory()
    p = (mem.get("plans") or {}).get(day)
    regime = p["regime"] if p else _classify(_lookback_features())[0]
    arm = mem.setdefault("regimes", {}).setdefault(regime, {}).setdefault(
        strategy, {"n": 0, "mean": 0.0})
    arm["n"] += 1
    arm["mean"] += (float(net_return_pct) - arm["mean"]) / arm["n"]   # incremental mean
    arm["mean"] = round(arm["mean"], 4)
    _save_memory(mem)
    return {"regime": regime, "strategy": strategy, "n": arm["n"], "mean": arm["mean"]}


def memory() -> dict:
    return _load_memory()
