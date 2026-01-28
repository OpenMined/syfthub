"""
Tests for configuration management.

This module tests the Settings class and load_settings function.
"""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest
from pydantic import SecretStr, ValidationError

from syfthub_api import Settings, load_settings


class TestSettings:
    """Tests for the Settings class."""

    def test_create_settings_with_all_required_fields(self) -> None:
        """Test creating Settings with all required fields."""
        settings = Settings(
            syfthub_url="http://localhost:8080",
            syfthub_username="user",
            syfthub_password="pass",
            space_url="http://localhost:8001",
        )
        assert settings.syfthub_url == "http://localhost:8080"
        assert settings.syfthub_username == "user"
        assert isinstance(settings.syfthub_password, SecretStr)
        assert settings.space_url == "http://localhost:8001"

    def test_settings_default_values(self) -> None:
        """Test that Settings has correct default values."""
        settings = Settings(
            syfthub_url="http://localhost:8080",
            syfthub_username="user",
            syfthub_password="pass",
            space_url="http://localhost:8001",
        )
        assert settings.log_level == "INFO"
        assert settings.server_host == "0.0.0.0"
        assert settings.server_port == 8000

    def test_settings_custom_optional_values(self) -> None:
        """Test Settings with custom optional values."""
        settings = Settings(
            syfthub_url="http://localhost:8080",
            syfthub_username="user",
            syfthub_password="pass",
            space_url="http://localhost:8001",
            log_level="DEBUG",
            server_host="127.0.0.1",
            server_port=9000,
        )
        assert settings.log_level == "DEBUG"
        assert settings.server_host == "127.0.0.1"
        assert settings.server_port == 9000

    def test_settings_missing_required_field_raises(self) -> None:
        """Test that missing required fields raise ValidationError."""
        with pytest.raises(ValidationError):
            Settings(
                syfthub_username="user",
                syfthub_password="pass",
                space_url="http://localhost:8001",
            )  # type: ignore - missing syfthub_url

    def test_get_password_returns_plain_text(self) -> None:
        """Test that get_password() returns the plain text password."""
        settings = Settings(
            syfthub_url="http://localhost:8080",
            syfthub_username="user",
            syfthub_password="my-secret-password",
            space_url="http://localhost:8001",
        )
        assert settings.get_password() == "my-secret-password"

    def test_password_hidden_in_repr(self) -> None:
        """Test that password is hidden in string representation."""
        settings = Settings(
            syfthub_url="http://localhost:8080",
            syfthub_username="user",
            syfthub_password="my-secret-password",
            space_url="http://localhost:8001",
        )
        repr_str = repr(settings)
        assert "my-secret-password" not in repr_str
        assert "**********" in repr_str


class TestLogLevelValidation:
    """Tests for log level validation."""

    @pytest.mark.parametrize("level", ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"])
    def test_valid_log_levels(self, level: str) -> None:
        """Test that valid log levels are accepted."""
        settings = Settings(
            syfthub_url="http://localhost:8080",
            syfthub_username="user",
            syfthub_password="pass",
            space_url="http://localhost:8001",
            log_level=level,
        )
        assert settings.log_level == level

    @pytest.mark.parametrize("level", ["debug", "info", "warning", "error", "critical"])
    def test_log_levels_normalized_to_uppercase(self, level: str) -> None:
        """Test that log levels are normalized to uppercase."""
        settings = Settings(
            syfthub_url="http://localhost:8080",
            syfthub_username="user",
            syfthub_password="pass",
            space_url="http://localhost:8001",
            log_level=level,
        )
        assert settings.log_level == level.upper()

    def test_invalid_log_level_raises(self) -> None:
        """Test that invalid log level raises ValidationError."""
        with pytest.raises(ValidationError, match="log_level must be one of"):
            Settings(
                syfthub_url="http://localhost:8080",
                syfthub_username="user",
                syfthub_password="pass",
                space_url="http://localhost:8001",
                log_level="INVALID",
            )


class TestURLValidation:
    """Tests for URL validation."""

    def test_http_url_accepted(self) -> None:
        """Test that http:// URLs are accepted."""
        settings = Settings(
            syfthub_url="http://localhost:8080",
            syfthub_username="user",
            syfthub_password="pass",
            space_url="http://localhost:8001",
        )
        assert settings.syfthub_url == "http://localhost:8080"

    def test_https_url_accepted(self) -> None:
        """Test that https:// URLs are accepted."""
        settings = Settings(
            syfthub_url="https://api.example.com",
            syfthub_username="user",
            syfthub_password="pass",
            space_url="https://space.example.com",
        )
        assert settings.syfthub_url == "https://api.example.com"

    def test_trailing_slash_removed(self) -> None:
        """Test that trailing slashes are removed from URLs."""
        settings = Settings(
            syfthub_url="http://localhost:8080/",
            syfthub_username="user",
            syfthub_password="pass",
            space_url="http://localhost:8001/",
        )
        assert settings.syfthub_url == "http://localhost:8080"
        assert settings.space_url == "http://localhost:8001"

    def test_invalid_url_scheme_raises(self) -> None:
        """Test that URLs without http/https raise ValidationError."""
        with pytest.raises(ValidationError, match="must start with http"):
            Settings(
                syfthub_url="ftp://localhost:8080",
                syfthub_username="user",
                syfthub_password="pass",
                space_url="http://localhost:8001",
            )

    def test_empty_url_raises(self) -> None:
        """Test that empty URLs raise ValidationError."""
        with pytest.raises(ValidationError, match="URL cannot be empty"):
            Settings(
                syfthub_url="",
                syfthub_username="user",
                syfthub_password="pass",
                space_url="http://localhost:8001",
            )


class TestServerPortValidation:
    """Tests for server port validation."""

    def test_valid_port_in_range(self) -> None:
        """Test that ports in valid range are accepted."""
        settings = Settings(
            syfthub_url="http://localhost:8080",
            syfthub_username="user",
            syfthub_password="pass",
            space_url="http://localhost:8001",
            server_port=8080,
        )
        assert settings.server_port == 8080

    def test_port_minimum_boundary(self) -> None:
        """Test minimum valid port (1)."""
        settings = Settings(
            syfthub_url="http://localhost:8080",
            syfthub_username="user",
            syfthub_password="pass",
            space_url="http://localhost:8001",
            server_port=1,
        )
        assert settings.server_port == 1

    def test_port_maximum_boundary(self) -> None:
        """Test maximum valid port (65535)."""
        settings = Settings(
            syfthub_url="http://localhost:8080",
            syfthub_username="user",
            syfthub_password="pass",
            space_url="http://localhost:8001",
            server_port=65535,
        )
        assert settings.server_port == 65535

    def test_port_below_minimum_raises(self) -> None:
        """Test that port below 1 raises ValidationError."""
        with pytest.raises(ValidationError):
            Settings(
                syfthub_url="http://localhost:8080",
                syfthub_username="user",
                syfthub_password="pass",
                space_url="http://localhost:8001",
                server_port=0,
            )

    def test_port_above_maximum_raises(self) -> None:
        """Test that port above 65535 raises ValidationError."""
        with pytest.raises(ValidationError):
            Settings(
                syfthub_url="http://localhost:8080",
                syfthub_username="user",
                syfthub_password="pass",
                space_url="http://localhost:8001",
                server_port=65536,
            )


class TestLoadSettings:
    """Tests for the load_settings function."""

    def test_load_settings_from_env_vars(self) -> None:
        """Test loading settings from environment variables."""
        env_vars = {
            "SYFTHUB_URL": "http://env.example.com",
            "SYFTHUB_USERNAME": "envuser",
            "SYFTHUB_PASSWORD": "envpass",
            "SPACE_URL": "http://space.env.com",
        }
        with patch.dict(os.environ, env_vars, clear=True):
            settings = load_settings()

        assert settings.syfthub_url == "http://env.example.com"
        assert settings.syfthub_username == "envuser"
        assert settings.get_password() == "envpass"
        assert settings.space_url == "http://space.env.com"

    def test_load_settings_with_overrides(self) -> None:
        """Test that overrides take precedence over env vars."""
        env_vars = {
            "SYFTHUB_URL": "http://env.example.com",
            "SYFTHUB_USERNAME": "envuser",
            "SYFTHUB_PASSWORD": "envpass",
            "SPACE_URL": "http://space.env.com",
            "LOG_LEVEL": "INFO",
        }
        with patch.dict(os.environ, env_vars, clear=True):
            settings = load_settings(log_level="DEBUG", server_port=9000)

        assert settings.log_level == "DEBUG"
        assert settings.server_port == 9000

    def test_load_settings_converts_port_from_env(self) -> None:
        """Test that SERVER_PORT env var is converted to int."""
        env_vars = {
            "SYFTHUB_URL": "http://env.example.com",
            "SYFTHUB_USERNAME": "envuser",
            "SYFTHUB_PASSWORD": "envpass",
            "SPACE_URL": "http://space.env.com",
            "SERVER_PORT": "9999",
        }
        with patch.dict(os.environ, env_vars, clear=True):
            settings = load_settings()

        assert settings.server_port == 9999
        assert isinstance(settings.server_port, int)

    def test_load_settings_missing_required_raises(self) -> None:
        """Test that missing required env vars raise ValidationError."""
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ValidationError):
                load_settings()

    def test_load_settings_partial_env_vars(self) -> None:
        """Test load_settings with partial env vars and overrides."""
        env_vars = {
            "SYFTHUB_URL": "http://env.example.com",
            "SYFTHUB_USERNAME": "envuser",
        }
        with patch.dict(os.environ, env_vars, clear=True):
            settings = load_settings(
                syfthub_password="override-pass",
                space_url="http://override.space.com",
            )

        assert settings.syfthub_url == "http://env.example.com"
        assert settings.syfthub_username == "envuser"
        assert settings.get_password() == "override-pass"
        assert settings.space_url == "http://override.space.com"
