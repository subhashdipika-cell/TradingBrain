from fastapi import FastAPI

from app.api.health import router as health_router
from app.core.config import settings
from app.core.lifespan import lifespan


tags_metadata = [
    {
        "name": "Health",
        "description": "System health and monitoring endpoints.",
    }
]


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
    prefix=settings.API_V1_PREFIX,
)


@app.get("/")
async def root():
    return {
        "application": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "status": "running",
    }