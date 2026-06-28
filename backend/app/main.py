from fastapi import FastAPI

from app.api.health import router as health_router
from app.core.config import settings
from app.core.logging import logger

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
)

app.include_router(health_router)

logger.info("TradingBrain backend started")


@app.get("/")
def root():
    return {
        "application": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "status": "running",
    }