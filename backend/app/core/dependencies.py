"""
Application dependency providers.

All reusable FastAPI dependencies should be defined here.

As the application grows, this module will provide:

- Database sessions
- Broker clients
- Market data providers
- Strategy engines
- Authentication
- Configuration
"""

from app.core.config import Settings, get_settings


def get_app_settings() -> Settings:
    """
    Return the application settings instance.

    Using a dependency makes configuration easy to mock during testing.
    """
    return get_settings()