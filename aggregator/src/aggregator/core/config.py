"""Configuration settings for the aggregator service."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Service identification
    service_name: str = "syfthub-aggregator"
    debug: bool = False

    # Logging & Observability
    log_level: str = "INFO"
    log_format: str = "json"  # "json" for production, "console" for development

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

    # Model streaming configuration
    # TODO: Set to True when SyftAI-Space implements model streaming.
    # Currently SyftAI-Space ignores the stream parameter and always returns
    # synchronous JSON responses. When this is enabled, the aggregator will
    # attempt to stream tokens from the model endpoint.
    model_streaming_enabled: bool = False

    # NATS configuration (for tunneling spaces)
    nats_url: str = "nats://nats:4222"
    nats_auth_token: str = ""
    nats_tunnel_timeout: float = 30.0

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
