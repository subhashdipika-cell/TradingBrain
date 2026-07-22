from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.core.logging import logger


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifecycle manager.

    Runs once during startup and once during shutdown.
    """

    logger.info("Starting TradingBrain Backend")

    # Keep-awake: Modern Standby (10-min on-battery sleep) killed the 07-21
    # auto run mid-flight and 5/6 backends that evening. Same pattern as the
    # AlphaEdge strategy-lab and the SMT/IntelliTrade backends. The dedicated
    # thread re-asserts every 60 s; released when the process exits.
    import threading

    def _keep_awake_loop():
        import ctypes
        import time as _t
        ES_CONTINUOUS, ES_SYSTEM_REQUIRED = 0x80000000, 0x00000001
        while True:
            try:
                ctypes.windll.kernel32.SetThreadExecutionState(
                    ES_CONTINUOUS | ES_SYSTEM_REQUIRED)
            except Exception as exc:
                logger.warning("Keep-awake failed: %s", exc)
                return
            _t.sleep(60)

    threading.Thread(target=_keep_awake_loop, daemon=True, name="keep-awake").start()
    logger.info("Keep-awake ON - system held out of standby while backend runs.")

    # Autonomous daily forward trading — brain-decided, hands-free.
    from app.workers.auto_trader import start_auto_trader
    start_auto_trader()

    # Future initialization:
    # - Database
    # - Redis
    # - Broker APIs
    # - WebSocket manager

    yield

    logger.info("Stopping TradingBrain Backend")

    # Future cleanup:
    # - Close database
    # - Stop schedulers
    # - Disconnect brokers