"""
Configuration management for the SyftHub API framework.

This module provides a Settings class for managing application configuration
using environment variables and .env files.

Example:
    from syfthub_api.config import Settings, load_settings

    # Load from environment variables
    settings = load_settings()

    # Or with overrides
    settings = load_settings(log_level="DEBUG", server_port=9000)

    # Or construct directly
    settings = Settings(
        syfthub_url="http://localhost:8080",
        syfthub_username="user",
        syfthub_password="pass",
        space_url="http://localhost:8001",
    )
"""

from __future__ import annotations

import os
from typing import Annotated

from pydantic import BaseModel, Field, SecretStr, field_validator

# Tunneling URL prefix
TUNNELING_PREFIX = "tunneling:"


class Settings(BaseModel):
    """
    Configuration settings for SyftAPI.

    Settings can be provided via:
    1. Constructor arguments
    2. Environment variables
    3. The load_settings() factory function

    Attributes:
        syfthub_url: URL of the SyftHub backend.
        syfthub_username: SyftHub username for authentication.
        syfthub_password: SyftHub password for authentication (stored securely).
        space_url: Public URL of this SyftAI Space.
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL).
        server_host: Host to bind the server to.
        server_port: Port to bind the server to.
    """

    # Required settings
    syfthub_url: Annotated[str, Field(description="URL of the SyftHub backend")]
    syfthub_username: Annotated[str, Field(min_length=1, description="SyftHub username")]
    syfthub_password: Annotated[SecretStr, Field(description="SyftHub password")]
    space_url: Annotated[str, Field(description="Public URL of this SyftAI Space")]

    # Optional settings with defaults
    log_level: Annotated[str, Field(default="INFO", description="Logging level")] = "INFO"
    server_host: Annotated[str, Field(default="0.0.0.0", description="Server host")] = "0.0.0.0"
    server_port: Annotated[int, Field(default=8000, ge=1, le=65535, description="Server port")] = (
        8000
    )

    # Heartbeat settings
    heartbeat_enabled: Annotated[
        bool, Field(default=True, description="Enable periodic heartbeat to SyftHub")
    ] = True
    heartbeat_ttl_seconds: Annotated[
        int,
        Field(
            default=300,
            ge=1,
            le=3600,
            description="Heartbeat TTL in seconds (server caps at 600)",
        ),
    ] = 300
    heartbeat_interval_multiplier: Annotated[
        float,
        Field(
            default=0.8,
            gt=0.0,
            lt=1.0,
            description="Send heartbeat at TTL * multiplier (e.g., 0.8 = 80% of TTL)",
        ),
    ] = 0.8

    @property
    def is_tunneling(self) -> bool:
        """Check if running in tunneling mode based on space_url."""
        return self.space_url.startswith(TUNNELING_PREFIX)

    @property
    def tunnel_username(self) -> str | None:
        """Extract username from tunneling URL, or None if not tunneling."""
        if self.is_tunneling:
            return self.space_url[len(TUNNELING_PREFIX) :]
        return None

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """Validate and normalize log level."""
        valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        normalized = v.upper()
        if normalized not in valid_levels:
            raise ValueError(f"log_level must be one of {valid_levels}, got '{v}'")
        return normalized

    @field_validator("syfthub_url")
    @classmethod
    def validate_syfthub_url(cls, v: str) -> str:
        """Validate SyftHub URL format (must be HTTP/HTTPS)."""
        if not v:
            raise ValueError("URL cannot be empty")
        if not v.startswith(("http://", "https://")):
            raise ValueError(f"URL must start with http:// or https://, got '{v}'")
        return v.rstrip("/")  # Normalize by removing trailing slash

    @field_validator("space_url")
    @classmethod
    def validate_space_url(cls, v: str) -> str:
        """Validate space URL format (HTTP/HTTPS or tunneling:<username>)."""
        if not v:
            raise ValueError("URL cannot be empty")

        # Check for tunneling mode
        if v.startswith(TUNNELING_PREFIX):
            username = v[len(TUNNELING_PREFIX) :]
            if not username:
                raise ValueError("Tunneling username cannot be empty")
            if len(username) > 50:
                raise ValueError("Tunneling username cannot exceed 50 characters")
            # Basic username validation (alphanumeric, underscores, hyphens)
            if not all(c.isalnum() or c in "_-" for c in username):
                raise ValueError(
                    "Tunneling username can only contain alphanumeric characters, "
                    "underscores, and hyphens"
                )
            return v  # Return as-is for tunneling

        # Standard HTTP URL validation
        if not v.startswith(("http://", "https://")):
            raise ValueError(
                f"URL must start with http://, https://, or {TUNNELING_PREFIX}, got '{v}'"
            )
        return v.rstrip("/")  # Normalize by removing trailing slash

    def get_password(self) -> str:
        """Get the password value (for use in SDK calls)."""
        return self.syfthub_password.get_secret_value()


def load_settings(**overrides: str | int) -> Settings:
    """
    Load settings from environment variables with optional overrides.

    This function reads configuration from environment variables and allows
    overriding specific values through keyword arguments.

    Environment Variables:
        SYFTHUB_URL: URL of the SyftHub backend
        SYFTHUB_USERNAME: SyftHub username
        SYFTHUB_PASSWORD: SyftHub password
        SPACE_URL: Public URL of this SyftAI Space
        LOG_LEVEL: Logging level (default: INFO)
        SERVER_HOST: Server host (default: 0.0.0.0)
        SERVER_PORT: Server port (default: 8000)
        HEARTBEAT_ENABLED: Enable periodic heartbeat (default: true)
        HEARTBEAT_TTL_SECONDS: Heartbeat TTL in seconds (default: 300)
        HEARTBEAT_INTERVAL_MULTIPLIER: Send at TTL * multiplier (default: 0.8)

    Args:
        **overrides: Keyword arguments to override environment variables.

    Returns:
        Configured Settings instance.

    Raises:
        ValidationError: If required settings are missing or invalid.

    Example:
        # Load from environment
        settings = load_settings()

        # Load with overrides
        settings = load_settings(log_level="DEBUG", server_port=9000)
    """
    # Build settings dict from environment variables
    env_mapping = {
        "syfthub_url": "SYFTHUB_URL",
        "syfthub_username": "SYFTHUB_USERNAME",
        "syfthub_password": "SYFTHUB_PASSWORD",
        "space_url": "SPACE_URL",
        "log_level": "LOG_LEVEL",
        "server_host": "SERVER_HOST",
        "server_port": "SERVER_PORT",
        "heartbeat_enabled": "HEARTBEAT_ENABLED",
        "heartbeat_ttl_seconds": "HEARTBEAT_TTL_SECONDS",
        "heartbeat_interval_multiplier": "HEARTBEAT_INTERVAL_MULTIPLIER",
    }

    settings_dict: dict[str, str | int | bool | float] = {}

    for setting_name, env_var in env_mapping.items():
        env_value = os.environ.get(env_var)
        if env_value is not None:
            # Convert types as needed
            if setting_name == "server_port" or setting_name == "heartbeat_ttl_seconds":
                settings_dict[setting_name] = int(env_value)
            elif setting_name == "heartbeat_enabled":
                settings_dict[setting_name] = env_value.lower() in ("true", "1", "yes")
            elif setting_name == "heartbeat_interval_multiplier":
                settings_dict[setting_name] = float(env_value)
            else:
                settings_dict[setting_name] = env_value

    # Apply overrides
    settings_dict.update(overrides)

    # Use model_validate to handle type coercion properly
    return Settings.model_validate(settings_dict)
