"""Application configuration."""

from functools import lru_cache
from typing import Any

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        env_nested_delimiter="__",
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

    # CORS settings - using string to avoid JSON parsing issues
    cors_origins_str: str = Field(default="*", alias="cors_origins")

    @field_validator("cors_origins_str", mode="before")
    @classmethod
    def validate_cors_origins(cls, v: Any) -> str:
        """Validate CORS origins environment variable."""
        if v is None or v == "":
            return "*"
        return str(v)

    @property
    def cors_origins(self) -> list[str]:
        """Get parsed CORS origins as list."""
        if not self.cors_origins_str or self.cors_origins_str.strip() == "":
            return ["*"]

        # Handle comma-separated string
        if "," in self.cors_origins_str:
            return [
                origin.strip()
                for origin in self.cors_origins_str.split(",")
                if origin.strip()
            ]

        # Single origin
        return (
            [self.cors_origins_str.strip()] if self.cors_origins_str.strip() else ["*"]
        )

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
