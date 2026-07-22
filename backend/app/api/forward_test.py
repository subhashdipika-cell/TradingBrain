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
    starting_capital: float = Field(default=400_000.0, gt=0)
    # Default must give the run a chance to actually TRADE. The old default
    # of 30 polls (~105 s) meant every morning-launched run finished half an
    # hour before the 10:15 entry-open cutoff — six zero-trade "forward
    # tests" in a row (07-13..07-22) were this, not strategy failures.
    max_polls: int = Field(default=5000, ge=1, le=5200,
                           description="Stop after N option-chain polls so the run ends and saves. "
                                       "Default covers a full session; entries only begin after "
                                       "the 10:15 IST open cutoff, so short runs cannot trade.")
    # "AUTO" = structure-aware regime selection; or a specific strategy TB001..TB006.
    strategy: str = "AUTO"


def _market_open() -> bool:
    return NSE_SESSION.is_open(datetime.now(IST))


def _now() -> str:
    return datetime.now(IST).isoformat(timespec="seconds")


def _worker(symbol: str, capital: float, strategy: str, max_polls: int) -> None:
    try:
        run_id = run_forward_test(
            symbol=symbol, starting_capital=capital,
            strategy=strategy, max_polls=max_polls,
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
              request.strategy, request.max_polls),
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


# ── AutoTrader (autonomous daily forward testing) control ────────────────────

class AutoTraderToggle(BaseModel):
    enabled: bool


@router.get("/auto-trader/status")
async def auto_trader_status() -> dict[str, object]:
    """AutoTrader runtime state: enabled, entry window, today's decision."""
    from app.workers import auto_trader
    st = auto_trader.status()
    with _lock:
        st["running"] = _state["running"]
    return st


@router.post("/auto-trader/toggle")
async def auto_trader_toggle(req: AutoTraderToggle) -> dict[str, object]:
    """Start/stop autonomous forward testing. Starting inside the entry window
    (10:20-14:30 IST) triggers today's brain run immediately; stopping only
    prevents NEW runs — a forward test already in flight completes and saves."""
    from app.workers import auto_trader
    st = auto_trader.set_enabled(req.enabled)
    with _lock:
        st["running"] = _state["running"]
    return st
