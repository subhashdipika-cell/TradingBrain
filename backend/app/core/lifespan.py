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