"""
TradingBrain
API - The Daily Brain

GET  /brain/plan    - today's plan: confirmed regime (2-3 day lookback),
                      chosen strategy or STAND_ASIDE, scoring + vault evidence.
GET  /brain/memory  - the learned regime->strategy memory (bandit state).
POST /brain/record  - manually feed an outcome back (forward tests do this
                      automatically when run with strategy="BRAIN").

Author: TradingBrain
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from app.domains.intelligence import daily_brain

router = APIRouter(prefix="/brain", tags=["brain"])


@router.get("/plan")
def get_plan(force: bool = False) -> dict:
    try:
        return daily_brain.plan(force=force)
    except Exception as exc:  # noqa: BLE001 — surface the reason, don't 500
        return {"error": str(exc)}


@router.get("/memory")
def get_memory() -> dict:
    return daily_brain.memory()


class OutcomeIn(BaseModel):
    strategy: str
    net_return_pct: float
    date: str | None = None


@router.post("/record")
def record(o: OutcomeIn) -> dict:
    return daily_brain.record_outcome(o.strategy, o.net_return_pct, o.date)
