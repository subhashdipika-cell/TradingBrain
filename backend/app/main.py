from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.health import router as health_router
from app.core.config import settings
from app.core.logging import logger


tags_metadata = [
    {
        "name": "Health",
        "description": "System health and monitoring endpoints.",
    }
]


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting TradingBrain Backend")
    yield
    logger.info("Stopping TradingBrain Backend")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="""
TradingBrain API

A modular trading platform for:

- Market Data
- Analysis
- Strategy
- Risk Management
- Backtesting
- MT5 Execution
- Trade Journaling
""",
    openapi_tags=tags_metadata,
    lifespan=lifespan,
)

app.include_router(
    health_router,
    prefix="/api/v1",
)


@app.get("/")
async def root():
    return {
        "application": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "status": "running",
    }