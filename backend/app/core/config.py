from functools import lru_cache

from pydantic import Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Central application configuration.
    """

    # ------------------------------------------------------------------
    # Application
    # ------------------------------------------------------------------

    APP_NAME: str = "TradingBrain"
    APP_VERSION: str = "0.1.0"
    ENVIRONMENT: str = "development"

    # ------------------------------------------------------------------
    # API
    # ------------------------------------------------------------------

    API_V1_PREFIX: str = "/api/v1"

    HOST: str = "0.0.0.0"
    PORT: int = Field(default=8200, ge=1, le=65535)

    # ------------------------------------------------------------------
    # Logging
    # ------------------------------------------------------------------

    LOG_LEVEL: str = "INFO"

    # ------------------------------------------------------------------
    # Database
    # ------------------------------------------------------------------

    DATABASE_HOST: str = "localhost"
    DATABASE_PORT: int = 5432
    DATABASE_NAME: str = "tradingbrain"
    DATABASE_USER: str = "postgres"
    DATABASE_PASSWORD: str = "postgres"
    DATABASE_ECHO: bool = False

    @computed_field
    @property
    def DATABASE_URL(self) -> str:
        return (
            f"postgresql+asyncpg://"
            f"{self.DATABASE_USER}:{self.DATABASE_PASSWORD}"
            f"@{self.DATABASE_HOST}:{self.DATABASE_PORT}"
            f"/{self.DATABASE_NAME}"
        )

    # ------------------------------------------------------------------
    # Broker - Dhan (live data + execution)
    # ------------------------------------------------------------------

    DHAN_CLIENT_ID: str = ""
    DHAN_ACCESS_TOKEN: str = ""

    # Directory of accumulated Dhan option-chain CSVs (e.g. AlphaEdge's
    # strategy-lab/data/options) for real-data backtests from the dashboard.
    DHAN_DATA_DIR: str = "D:/AlphaEdge/strategy-lab/data/options"

    # Optional AlphaEdge-style dhan_config.json ({access_token, client_id}) to
    # reuse existing credentials for live/forward testing.
    DHAN_CONFIG_PATH: str = "D:/AlphaEdge/strategy-lab/dhan_config.json"

    # Where backtest/forward-test run results are persisted (JSON per run).
    RESULTS_DIR: str = "results"

    # Autonomous forward trading (workers/auto_trader.py): once per trading
    # day the Daily Brain picks the strategy and a forward test runs on its
    # own inside the 10:20-14:30 IST window. STAND_ASIDE days are recorded,
    # not traded. Set AUTO_FORWARD_TEST=false in .env to disable.
    AUTO_FORWARD_TEST: bool = True
    AUTO_FT_CAPITAL: float = 400_000.0
    # Must span the entry window to the 15:15 square-off, else the run ends
    # early and force-closes an open position (e.g. an iron fly held only 14
    # min on 2026-07-08). At poll_seconds=3.5, a 10:20 start reaches 15:15 in
    # ~5057 polls — 5200 lets the engine hit its OWN 15:15 square-off first.
    AUTO_FT_MAX_POLLS: int = 5200

    # Obsidian vault "raw trades" root. TradingBrain writes its daily reports
    # and monthly rollups under <OBSIDIAN_TRADES_DIR>/tradingbrain/ for the vault
    # to ingest and analyse. Shared destination across the four trading apps.
    OBSIDIAN_TRADES_DIR: str = "E:/Obsidian/Trading_Mind/raw/trades"
    OBSIDIAN_APP: str = "tradingbrain"

    # ------------------------------------------------------------------
    # CORS
    # ------------------------------------------------------------------

    CORS_ALLOW_ORIGINS: list[str] = [
        "http://localhost:5174",
        "http://127.0.0.1:5174",
    ]

    CORS_ALLOW_CREDENTIALS: bool = True
    CORS_ALLOW_METHODS: list[str] = ["*"]
    CORS_ALLOW_HEADERS: list[str] = ["*"]

    # ------------------------------------------------------------------
    # Settings
    # ------------------------------------------------------------------

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
