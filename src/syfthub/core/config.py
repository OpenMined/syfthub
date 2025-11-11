"""Application configuration."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application settings
    app_name: str = "Syfthub API"
    debug: bool = False
    api_prefix: str = "/api/v1"

    # Server settings
    host: str = "0.0.0.0"
    port: int = 8000
    reload: bool = False
    workers: int = 1

    # CORS settings
    cors_origins: list[str] = ["*"]

    # Security settings
    secret_key: str = "your-secret-key-here-change-in-production"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7

    # Password settings
    password_min_length: int = 8

    # Database settings
    database_url: str = "sqlite:///./syfthub.db"
    database_echo: bool = False  # Echo SQL queries for debugging

    # Logging
    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


settings = get_settings()
