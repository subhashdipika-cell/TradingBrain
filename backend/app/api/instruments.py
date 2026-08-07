"""
TradingBrain
API - Instruments

Current index lot sizes and a one-click refresh from Dhan's scrip master (NSE/BSE
revise F&O lot sizes periodically). The download is I/O-bound, so the refresh
runs in a threadpool.
"""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.concurrency import run_in_threadpool

from app.domains.market import symbol

router = APIRouter(tags=["Instruments"])


@router.get("/instruments/lot-sizes")
async def get_lot_sizes() -> dict[str, object]:
    """Current effective lot size per instrument."""
    ov = symbol._load_overrides()
    return {"lots": symbol.lot_sizes(), "updated": ov.get("updated")}


@router.post("/instruments/lot-sizes/refresh")
async def refresh_lot_sizes() -> dict[str, object]:
    """Pull current index lot sizes from Dhan's scrip master and apply them."""
    return await run_in_threadpool(symbol.refresh_lot_sizes)
