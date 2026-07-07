"""
TradingBrain
Workers - Autonomous Forward Trader

Makes TradingBrain trade its forward tests WITHOUT a human trigger. Once per
trading day, inside the entry window (after the 10:15 open cutoff, before
14:30 so the session has room ahead of the 15:15 square-off):

  1. ask the Daily Brain for today's plan (multi-day regime + learned pick),
  2. honor STAND_ASIDE — an explicitly recorded no-trade decision,
  3. otherwise launch the SAME background forward-test runner the dashboard
     button uses (shared single-run guard, so manual and auto never collide).

The run lands in the results store (History/Analysis tabs) and its outcome
feeds the brain's regime memory — the full sense->decide->act->learn loop,
daily, hands-free. Disable with AUTO_FORWARD_TEST=false in .env.
"""

from __future__ import annotations

import json
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.core.config import settings
from app.core.logging import logger

IST = timezone(timedelta(hours=5, minutes=30))
STATE_FILE = Path(__file__).resolve().parents[1] / "data" / "auto_trader.json"

WINDOW_START_MIN = 10 * 60 + 20   # 10:20 IST — after the open cutoff
WINDOW_END_MIN   = 14 * 60 + 30   # last auto-start; square-off is 15:15
TICK_SECONDS = 180


def _state() -> dict:
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save(**patch) -> None:
    st = _state()
    st.update(patch)
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(st, indent=2), encoding="utf-8")


def _tick() -> None:
    now = datetime.now(IST)
    today = now.strftime("%Y-%m-%d")
    if _state().get("last_day") == today:
        return                                   # already decided/traded today
    mins = now.hour * 60 + now.minute
    if not (WINDOW_START_MIN <= mins <= WINDOW_END_MIN):
        return

    from app.domains.market.holidays import trading_day_check
    ok, why = trading_day_check()
    if not ok:
        _save(last_day=today, decision=f"skip: {why}")
        logger.info("AutoTrader: %s", why)
        return

    from app.domains.intelligence import daily_brain
    plan = daily_brain.plan()
    if plan["strategy"] == "STAND_ASIDE":
        _save(last_day=today,
              decision=f"STAND_ASIDE ({plan['regime']}): {plan['reason']}")
        logger.info("AutoTrader: brain stands aside today (%s) — %s",
                    plan["regime"], plan["reason"])
        return

    # Launch through the dashboard's runner so the single-run guard holds.
    from app.api import forward_test as ft
    with ft._lock:
        if ft._state["running"]:
            return                               # manual run active — retry next tick
        ft._state.update(running=True, started_at=ft._now(), finished_at=None,
                         symbol="NIFTY", last_run_id=None, error=None)
    _save(last_day=today, started=ft._now(),
          decision=f"run {plan['strategy']} ({plan['regime']})")
    logger.info("AutoTrader: launching brain forward test — regime=%s pick=%s",
                plan["regime"], plan["strategy"])
    threading.Thread(
        target=ft._worker,
        args=("NIFTY", settings.AUTO_FT_CAPITAL, "BRAIN", settings.AUTO_FT_MAX_POLLS),
        daemon=True,
    ).start()


def _month_end_export() -> None:
    """On the LAST day of each month, after the close (>=15:40 IST), write the
    month's trade rollup to the Obsidian vault
    (<OBSIDIAN_TRADES_DIR>/tradingbrain/<YYYY-MM>.md) — same output as the
    History tab's Export -> Obsidian button, just automatic."""
    now = datetime.now(IST)
    month = now.strftime("%Y-%m")
    if _state().get("last_export_month") == month:
        return
    is_last_day = (now + timedelta(days=1)).month != now.month
    if not is_last_day or (now.hour * 60 + now.minute) < 15 * 60 + 40:
        return
    try:
        from app.api.reports import _records
        from app.domains.analytics import obsidian_export as ox
        recs = _records(month=month)
        if recs:
            path = ox.write_export(month, ox.monthly_markdown(recs, month))
            logger.info("AutoTrader: month-end Obsidian export -> %s (%d runs)",
                        path, len(recs))
        else:
            logger.info("AutoTrader: month-end export skipped — no runs in %s", month)
        _save(last_export_month=month)
    except Exception as exc:  # noqa: BLE001 — retried next tick until the day ends
        logger.warning("AutoTrader month-end export failed: %s", exc)


def is_enabled() -> bool:
    """Runtime switch — Settings page start/stop persists here; the
    AUTO_FORWARD_TEST env value is only the default for a fresh state file."""
    return bool(_state().get("enabled", settings.AUTO_FORWARD_TEST))


def set_enabled(on: bool) -> dict:
    _save(enabled=bool(on))
    logger.info("AutoTrader %s from Settings.", "ENABLED" if on else "DISABLED")
    if on:
        # Start immediately when switched on inside the entry window (and the
        # brain hasn't already decided today) instead of waiting for the tick.
        threading.Thread(target=_tick, daemon=True).start()
    return status()


def status() -> dict:
    st = _state()
    now = datetime.now(IST)
    mins = now.hour * 60 + now.minute
    return {
        "enabled": is_enabled(),
        "in_window": WINDOW_START_MIN <= mins <= WINDOW_END_MIN,
        "window": "10:20-14:30 IST",
        "last_day": st.get("last_day"),
        "decision": st.get("decision"),
        "last_export_month": st.get("last_export_month"),
    }


def _loop() -> None:
    while True:
        try:
            if is_enabled():
                _tick()
            _month_end_export()
        except Exception as exc:  # noqa: BLE001 — the loop must survive anything
            logger.warning("AutoTrader tick failed: %s", exc)
        time.sleep(TICK_SECONDS)


def start_auto_trader() -> None:
    threading.Thread(target=_loop, daemon=True, name="auto-trader").start()
    logger.info("AutoTrader started (daily, window 10:20-14:30 IST, brain-driven, "
                "AUTO_FORWARD_TEST=%s).", settings.AUTO_FORWARD_TEST)
