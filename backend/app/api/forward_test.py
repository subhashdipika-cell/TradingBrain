"""
TradingBrain
API - Forward Test

Triggers a Dhan live-paper (forward) test from the dashboard. The run polls the
live option chain and can take a while, so it executes in a background thread;
the result lands in the results store (Analysis / Reports) when finished. Costs
are always applied (PaperBroker uses the full Indian options charge stack).
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.application.forward_test import run_forward_test
from app.domains.market.session import NSE_SESSION

router = APIRouter(tags=["Forward Test"])
log = logging.getLogger("tradingbrain.api.forward")

IST = timezone(timedelta(hours=5, minutes=30))

# Single-run guard + last-run state, shared across requests (one forward test at
# a time is plenty for a manual trigger).
_state: dict[str, object] = {
    "running": False, "started_at": None, "finished_at": None,
    "symbol": None, "last_run_id": None, "error": None,
}
_lock = threading.Lock()


class ForwardTestRequest(BaseModel):
    symbol: str = "NIFTY"
    starting_capital: float = Field(default=1_000_000.0, gt=0)
    max_polls: int = Field(default=30, ge=1, le=5000,
                           description="Stop after N option-chain polls so the run ends and saves.")
    single_strategy: bool = False


def _market_open() -> bool:
    return NSE_SESSION.is_open(datetime.now(IST))


def _now() -> str:
    return datetime.now(IST).isoformat(timespec="seconds")


def _worker(symbol: str, capital: float, use_selector: bool, max_polls: int) -> None:
    try:
        run_id = run_forward_test(
            symbol=symbol, starting_capital=capital,
            use_selector=use_selector, max_polls=max_polls,
        )
        with _lock:
            _state.update(last_run_id=run_id, error=None)
    except Exception as exc:  # noqa: BLE001 - surface any failure to the UI
        log.exception("Forward test failed")
        with _lock:
            _state.update(error=str(exc))
    finally:
        with _lock:
            _state.update(running=False, finished_at=_now())


@router.post("/forward-test/run")
async def start_forward_test(request: ForwardTestRequest) -> dict[str, object]:
    """Kick off a forward test in the background. Returns immediately."""
    with _lock:
        if _state["running"]:
            raise HTTPException(status_code=409, detail="A forward test is already running.")
        _state.update(running=True, started_at=_now(), finished_at=None,
                      symbol=request.symbol.upper(), last_run_id=None, error=None)

    threading.Thread(
        target=_worker,
        args=(request.symbol, request.starting_capital,
              not request.single_strategy, request.max_polls),
        daemon=True,
    ).start()

    open_now = _market_open()
    return {
        "status": "started",
        "symbol": request.symbol.upper(),
        "max_polls": request.max_polls,
        "market_open": open_now,
        "note": None if open_now else (
            "NSE is closed — the live option chain won't return fresh data. Run "
            "during market hours (Mon-Fri 09:15-15:30 IST) for meaningful fills."),
    }


@router.get("/forward-test/status")
async def forward_test_status() -> dict[str, object]:
    """Poll the current/last forward-test run state."""
    with _lock:
        st = dict(_state)
    st["market_open"] = _market_open()
    return st
