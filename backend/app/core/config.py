from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Central application configuration.

    Values are loaded from the .env file when present and fall back
    to the defaults defined here.
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
    # Pydantic Settings
    # ------------------------------------------------------------------

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    """
    Return a cached Settings instance.
    """
    return Settings()


settings = get_settings()