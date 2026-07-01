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

from dataclasses import dataclass

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
    lot_size=75,
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
