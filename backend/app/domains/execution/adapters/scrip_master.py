"""
TradingBrain
Execution - Dhan Scrip Master

Resolves an option leg (underlying, expiry, strike, right) to its Dhan
``security_id`` and ``exchange_segment`` - the identifiers ``place_order``
needs. Dhan publishes a CSV "scrip master" (the same file AlphaEdge caches as
``dhan_scrip_master.csv``); this loads the OPTIDX rows and indexes them.

Columns used: ``EXCH_ID, SECURITY_ID, INSTRUMENT, UNDERLYING_SYMBOL,
SYMBOL_NAME, LOT_SIZE, SM_EXPIRY_DATE, STRIKE_PRICE, OPTION_TYPE``.

Author: TradingBrain
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date

from app.domains.shared.enums import OptionRight

# Dhan exchange-segment codes for F&O by exchange.
_SEGMENT_BY_EXCH = {
    "NSE": "NSE_FNO",
    "BSE": "BSE_FNO",
}

_OPTION_INSTRUMENTS = {"OPTIDX", "OPTSTK", "OPTFUT", "OPTCUR"}


@dataclass(frozen=True, slots=True)
class ScripInfo:
    security_id: int
    exchange_segment: str
    lot_size: int
    tradingsymbol: str


def _norm_strike(value: str) -> float:
    return round(float(value), 2)


class ScripMaster:
    """Loads and indexes the Dhan scrip master for option lookups."""

    def __init__(self, path: str) -> None:
        self._path = path
        self._index: dict[tuple[str, str, float, str], ScripInfo] | None = None

    # ------------------------------------------------------------------
    def _ensure_loaded(self) -> dict[tuple[str, str, float, str], ScripInfo]:
        if self._index is not None:
            return self._index

        index: dict[tuple[str, str, float, str], ScripInfo] = {}
        with open(self._path, newline="", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                instrument = (row.get("INSTRUMENT") or "").strip().upper()
                if instrument not in _OPTION_INSTRUMENTS:
                    continue
                opt_type = (row.get("OPTION_TYPE") or "").strip().upper()
                if opt_type not in ("CE", "PE"):
                    continue
                underlying = (row.get("UNDERLYING_SYMBOL") or "").strip().upper()
                expiry = (row.get("SM_EXPIRY_DATE") or "").strip()
                try:
                    strike = _norm_strike(row["STRIKE_PRICE"])
                    security_id = int(float(row["SECURITY_ID"]))
                    lot_size = int(float(row.get("LOT_SIZE") or 0))
                except (KeyError, ValueError):
                    continue
                exch = (row.get("EXCH_ID") or "").strip().upper()
                key = (underlying, expiry, strike, opt_type)
                index[key] = ScripInfo(
                    security_id=security_id,
                    exchange_segment=_SEGMENT_BY_EXCH.get(exch, f"{exch}_FNO"),
                    lot_size=lot_size,
                    tradingsymbol=(row.get("SYMBOL_NAME") or "").strip(),
                )
        self._index = index
        return index

    # ------------------------------------------------------------------
    def resolve(
        self,
        *,
        underlying: str,
        expiry: date,
        strike: float,
        right: OptionRight,
    ) -> ScripInfo | None:
        """Return the :class:`ScripInfo` for an option leg, or ``None``."""
        index = self._ensure_loaded()
        opt_type = "CE" if right is OptionRight.CALL else "PE"
        key = (underlying.upper(), expiry.isoformat(), round(strike, 2), opt_type)
        return index.get(key)

    def __len__(self) -> int:
        return len(self._ensure_loaded())
