"""Application configuration."""

from functools import lru_cache
from typing import Any, Optional, Set

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

    # ===========================================
    # IDENTITY PROVIDER (IdP) SETTINGS
    # ===========================================

    # Issuer URL for JWT 'iss' claim
    issuer_url: str = "https://hub.syft.com"

    # RSA Key Configuration - Keys can be provided via:
    # 1. Base64-encoded PEM strings (environment variables)
    # 2. File paths to PEM files
    # 3. Auto-generation in development mode
    rsa_private_key_pem: Optional[str] = Field(
        default=None,
        description="Base64-encoded RSA private key PEM",
    )
    rsa_public_key_pem: Optional[str] = Field(
        default=None,
        description="Base64-encoded RSA public key PEM",
    )
    rsa_private_key_path: Optional[str] = Field(
        default=None,
        description="Path to RSA private key PEM file",
    )
    rsa_public_key_path: Optional[str] = Field(
        default=None,
        description="Path to RSA public key PEM file",
    )
    rsa_key_id: str = Field(
        default="hub-key-1",
        description="Key ID for JWKS (kid claim)",
    )
    rsa_key_size: int = Field(
        default=2048,
        description="RSA key size in bits for auto-generation",
    )

    # Satellite Token Settings
    satellite_token_expire_seconds: int = Field(
        default=60,
        description="Satellite token lifetime in seconds (short-lived)",
    )

    # Audience Allowlist - DEPRECATED: Now dynamically generated from user database
    # This static list is kept as a fallback for backward compatibility only.
    # In the new model, any active user's username is automatically a valid audience.
    # This list is only used when database lookup is not available.
    allowed_audiences_str: str = Field(
        default="",
        alias="allowed_audiences",
        description="DEPRECATED: Comma-separated list of fallback audience identifiers. "
        "Audiences are now dynamically generated from active user accounts.",
    )

    @field_validator("allowed_audiences_str", mode="before")
    @classmethod
    def validate_allowed_audiences(cls, v: Any) -> str:
        """Validate allowed audiences environment variable."""
        if v is None:
            return ""
        return str(v)

    @property
    def allowed_audiences(self) -> Set[str]:
        """Get parsed allowed audiences as a set.

        DEPRECATED: This property returns the static fallback list.
        Use validate_audience() with a UserRepository for dynamic validation.

        In the new model:
        - Audiences are dynamically validated against the user database
        - Any active user's username is a valid audience
        - This static list is only used as a fallback when DB is unavailable
        """
        if not self.allowed_audiences_str or self.allowed_audiences_str.strip() == "":
            return set()  # Empty set - no static fallback by default

        return {
            aud.strip().lower()
            for aud in self.allowed_audiences_str.split(",")
            if aud.strip()
        }

    # Development Mode - auto-generate RSA keys if not provided
    auto_generate_rsa_keys: bool = Field(
        default=True,
        description="Auto-generate RSA keys if not provided (dev mode only)",
    )

    # ===========================================
    # ACCOUNTING SERVICE SETTINGS
    # ===========================================

    # Default accounting service URL - used if user doesn't provide one during registration
    # Uses OpenMined's hosted accounting service by default
    default_accounting_url: Optional[str] = Field(
        default="https://syftaccounting.centralus.cloudapp.azure.com",
        description="Default accounting service URL for user registration",
    )

    # Generated accounting password length
    accounting_password_length: int = Field(
        default=32,
        description="Length of auto-generated accounting passwords",
    )

    # Timeout for accounting service requests
    accounting_timeout: float = Field(
        default=30.0,
        description="Timeout in seconds for accounting service requests",
    )


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


settings = get_settings()
