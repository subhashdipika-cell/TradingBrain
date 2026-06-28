from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Application configuration.

    Values are loaded from the .env file and can be
    overridden by environment variables.
    """

    APP_NAME: str = Field(default="TradingBrain")
    APP_VERSION: str = Field(default="0.1.0")
    ENVIRONMENT: str = Field(default="development")

    API_V1_PREFIX: str = Field(default="/api/v1")

    HOST: str = Field(default="0.0.0.0")
    PORT: int = Field(default=8000)

    LOG_LEVEL: str = Field(default="INFO")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
    )


@lru_cache
def get_settings() -> Settings:
    """
    Returns a cached Settings instance.

    The application should use this function
    instead of instantiating Settings directly.
    """
    return Settings()


settings = get_settings()