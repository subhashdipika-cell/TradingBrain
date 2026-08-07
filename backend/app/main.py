from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.backtest import router as backtest_router
from app.api.database import router as database_router
from app.api.health import router as health_router
from app.core.config import settings
from app.core.exceptions import TradingBrainException
from app.core.handlers import tradingbrain_exception_handler
from app.core.lifespan import lifespan
from app.middleware.request_context import RequestContextMiddleware

tags_metadata = [
    {
        "name": "Health",
        "description": "System health and monitoring endpoints.",
    },
    {
        "name": "Database",
        "description": "Database connectivity endpoints.",
    },
    {
        "name": "Backtest",
        "description": "Run TB001 backtests and retrieve performance metrics.",
    },
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

# ---------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------

app.add_middleware(RequestContextMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ALLOW_ORIGINS,
    allow_credentials=settings.CORS_ALLOW_CREDENTIALS,
    allow_methods=settings.CORS_ALLOW_METHODS,
    allow_headers=settings.CORS_ALLOW_HEADERS,
)

# ---------------------------------------------------------------------
# Exception Handlers
# ---------------------------------------------------------------------

app.add_exception_handler(
    TradingBrainException,
    tradingbrain_exception_handler,
)

# ---------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------

app.include_router(
    health_router,
    prefix=settings.API_V1_PREFIX,
)

app.include_router(
    database_router,
    prefix=settings.API_V1_PREFIX,
)

app.include_router(
    backtest_router,
    prefix=settings.API_V1_PREFIX,
)

# ---------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------

@app.get("/", tags=["Root"])
async def root():
    return {
        "application": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "status": "running",
    }