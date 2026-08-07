"""
TradingBrain
Market - Instrument Specifications

Static contract specifications for the index-option underlyings TB001
trades. Keeping lot sizes, strike steps and tick sizes in one place avoids
magic numbers scattered through the strategy and execution layers.

Lot sizes reflect NSE F&O contract specs and are revised by the exchange
periodically; update here when the exchange changes them.

Author: TradingBrain
"""

from __future__ import annotations

import csv
import io
import json
import os
import urllib.request
from dataclasses import dataclass, replace
from datetime import datetime, timezone

from app.domains.shared.enums import AssetClass


@dataclass(frozen=True, slots=True)
class InstrumentSpec:
    """Static specification for a tradable underlying."""

    symbol: str
    exchange: str
    asset_class: AssetClass
    lot_size: int
    strike_step: float
    tick_size: float = 0.05
    currency: str = "INR"

    def round_strike(self, price: float) -> float:
        """Nearest valid strike for ``price``."""
        return round(price / self.strike_step) * self.strike_step

    def atm_strike(self, spot: float) -> float:
        """At-the-money strike for the current spot."""
        return self.round_strike(spot)


# ---------------------------------------------------------------------
# Registry of supported underlyings
# ---------------------------------------------------------------------

NIFTY = InstrumentSpec(
    symbol="NIFTY",
    exchange="NSE",
    asset_class=AssetClass.OPTIONS,
    lot_size=65,
    strike_step=50.0,
)

BANKNIFTY = InstrumentSpec(
    symbol="BANKNIFTY",
    exchange="NSE",
    asset_class=AssetClass.OPTIONS,
    lot_size=30,
    strike_step=100.0,
)

FINNIFTY = InstrumentSpec(
    symbol="FINNIFTY",
    exchange="NSE",
    asset_class=AssetClass.OPTIONS,
    lot_size=65,
    strike_step=50.0,
)

SENSEX = InstrumentSpec(
    symbol="SENSEX",
    exchange="BSE",
    asset_class=AssetClass.OPTIONS,
    lot_size=20,
    strike_step=100.0,
)


_REGISTRY: dict[str, InstrumentSpec] = {
    spec.symbol: spec for spec in (NIFTY, BANKNIFTY, FINNIFTY, SENSEX)
}

# Aliases used by external data sources (e.g. Dhan/AlphaEdge feeds).
_ALIASES: dict[str, str] = {
    "NIFTY50": "NIFTY",
    "NIFTY 50": "NIFTY",
    "BANKNIFTY": "BANKNIFTY",
    "NIFTYBANK": "BANKNIFTY",
}


def _resolve(symbol: str) -> str:
    key = symbol.upper().strip()
    return _ALIASES.get(key, key)


def get_instrument(symbol: str) -> InstrumentSpec:
    """Look up an :class:`InstrumentSpec` by symbol or alias (case-insensitive)."""
    key = _resolve(symbol)
    if key not in _REGISTRY:
        raise KeyError(f"Unknown instrument '{symbol}'.")
    return _REGISTRY[key]


def is_supported(symbol: str) -> bool:
    return _resolve(symbol) in _REGISTRY


def supported_symbols() -> list[str]:
    return sorted(_REGISTRY.keys())


# ---------------------------------------------------------------------
# Live lot sizes from Dhan's scrip master
# ---------------------------------------------------------------------
# NSE/BSE revise F&O lot sizes periodically. Rather than rely on the static
# values above, the dashboard can pull the current lot sizes from Dhan's public
# scrip master and persist them here as overrides applied over the registry.
DHAN_SCRIP_MASTER_URL = "https://images.dhan.co/api-data/api-scrip-master.csv"
_INDEX_UNDERLYINGS = {
    "NIFTY", "BANKNIFTY", "FINNIFTY", "SENSEX", "MIDCPNIFTY", "BANKEX",
    "NIFTYNXT50", "SENSEX50",
}
_OVERRIDES_PATH = os.path.join(os.path.dirname(__file__), "lot_overrides.json")


def _load_overrides() -> dict:
    try:
        with open(_OVERRIDES_PATH, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError):
        return {}


def _apply_overrides() -> None:
    """Override registry lot sizes from the persisted Dhan snapshot, if any."""
    for sym, lot in (_load_overrides().get("lots") or {}).items():
        key = _resolve(sym)
        if key in _REGISTRY and isinstance(lot, (int, float)) and lot > 0:
            _REGISTRY[key] = replace(_REGISTRY[key], lot_size=int(lot))


def lot_sizes() -> dict[str, int]:
    """Current effective lot size per registered instrument."""
    return {sym: spec.lot_size for sym, spec in _REGISTRY.items()}


def refresh_lot_sizes() -> dict:
    """Download Dhan's scrip master, extract index option lot sizes, persist and
    apply them. Returns {ok, lots, updated, applied} | {ok:False, error}."""
    try:
        req = urllib.request.Request(DHAN_SCRIP_MASTER_URL, headers={"User-Agent": "TradingBrain"})
        with urllib.request.urlopen(req, timeout=60) as resp:
            text = resp.read().decode("utf-8", "replace")
    except Exception as exc:  # noqa: BLE001 - surface any download failure
        return {"ok": False, "error": f"scrip master download failed: {exc}"}

    lots: dict[str, int] = {}
    for row in csv.DictReader(io.StringIO(text)):
        if (row.get("SEM_INSTRUMENT_NAME") or "").strip().upper() != "OPTIDX":
            continue
        under = (row.get("SEM_TRADING_SYMBOL") or "").strip().upper().split("-")[0]
        if under not in _INDEX_UNDERLYINGS or under in lots:
            continue
        try:
            lot = int(float(row.get("SEM_LOT_UNITS") or 0))
        except ValueError:
            continue
        if lot > 0:
            lots[under] = lot
    if not lots:
        return {"ok": False, "error": "no OPTIDX lot sizes found in scrip master"}

    updated = datetime.now(timezone.utc).isoformat(timespec="seconds")
    try:
        with open(_OVERRIDES_PATH, "w", encoding="utf-8") as fh:
            json.dump({"lots": lots, "updated": updated}, fh, indent=2)
    except OSError as exc:
        return {"ok": False, "error": f"could not save overrides: {exc}"}

    _apply_overrides()
    return {"ok": True, "lots": lots, "updated": updated, "applied": lot_sizes()}


# Apply any persisted overrides at import so runs use the freshest lot sizes.
_apply_overrides()
