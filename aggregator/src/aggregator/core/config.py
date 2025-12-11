"""Configuration settings for the aggregator service."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Service identification
    service_name: str = "syfthub-aggregator"
    debug: bool = False

    # Server configuration
    host: str = "0.0.0.0"
    port: int = 8001

    # SyftHub integration
    syfthub_url: str = "http://localhost:8000"
    syfthub_jwks_cache_ttl: int = 3600  # seconds (1 hour)

    # Timeouts (seconds)
    retrieval_timeout: float = 30.0
    generation_timeout: float = 120.0
    total_timeout: float = 180.0

    # Retrieval configuration
    default_top_k: int = 5
    max_top_k: int = 20
    max_data_sources: int = 10

    # CORS configuration
    cors_origins: list[str] = ["*"]

    model_config = SettingsConfigDict(
        env_prefix="AGGREGATOR_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
