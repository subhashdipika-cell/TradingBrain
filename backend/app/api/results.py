"""
TradingBrain
API - Results / Analysis

Lists and serves saved backtest + forward-test runs for the dashboard's
analysis page.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, HTTPException

from app.application.results_store import ResultsStore
from app.core.config import settings

router = APIRouter(tags=["Results"])

_store = ResultsStore(settings.RESULTS_DIR)


@router.get("/results")
async def list_results() -> dict[str, list[dict[str, Any]]]:
    """List saved runs (most recent first) with headline metrics."""
    return {"results": [asdict(r) for r in _store.list()]}


@router.get("/results/{run_id}")
async def get_result(run_id: str) -> dict[str, Any]:
    """Return the full saved record for one run."""
    record = _store.get(run_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Result '{run_id}' not found.")
    return record
