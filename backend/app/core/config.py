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
