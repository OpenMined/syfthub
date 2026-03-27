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
    cors_origins_str: str = Field(
        default="http://localhost:3000,http://localhost:8080", alias="cors_origins"
    )

    @field_validator("cors_origins_str", mode="before")
    @classmethod
    def validate_cors_origins(cls, v: Any) -> str:
        """Validate CORS origins environment variable."""
        if v is None or v == "":
            return "http://localhost:3000,http://localhost:8080"
        return str(v)

    @property
    def cors_origins(self) -> list[str]:
        """Get parsed CORS origins as list."""
        if not self.cors_origins_str or self.cors_origins_str.strip() == "":
            return ["http://localhost:3000", "http://localhost:8080"]

        # Handle comma-separated string
        if "," in self.cors_origins_str:
            return [
                origin.strip()
                for origin in self.cors_origins_str.split(",")
                if origin.strip()
            ]

        # Single origin
        return (
            [self.cors_origins_str.strip()]
            if self.cors_origins_str.strip()
            else ["http://localhost:3000", "http://localhost:8080"]
        )

    # Security settings
    secret_key: str = "your-secret-key-here-change-in-production"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7

    # Encryption key for sensitive fields (Fernet key, base64-encoded 32 bytes).
    # Generate with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    # If unset, a deterministic key is derived from secret_key (NOT recommended for production).
    accounting_encryption_key: Optional[str] = Field(
        default=None,
        description="Fernet encryption key for accounting passwords. Generate with Fernet.generate_key().",
    )

    # Password settings
    password_min_length: int = 8

    # Database settings
    database_url: str = "sqlite:///./syfthub.db"
    database_echo: bool = False  # Echo SQL queries for debugging

    # ===========================================
    # LOGGING & OBSERVABILITY SETTINGS
    # ===========================================

    # Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    log_level: str = "INFO"

    # Log format ("json" for production, "console" for development)
    log_format: str = Field(
        default="json",
        description="Log output format: 'json' for structured logs, 'console' for human-readable",
    )

    # Whether to capture request/response bodies in logs
    log_request_body: bool = Field(
        default=False,
        description="Include request body in logs (may contain sensitive data)",
    )
    log_response_body: bool = Field(
        default=False,
        description="Include response body in error logs",
    )

    # Error log retention
    error_retention_days: int = Field(
        default=30,
        description="Number of days to retain error logs in the database",
    )

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

    # Directory for persisting auto-generated RSA keys (multi-worker support)
    # When auto-generating keys, they are saved to this directory so all workers
    # in a multi-process deployment share the same keys.
    rsa_keys_directory: str = Field(
        default="./data/rsa_keys",
        description="Directory to persist auto-generated RSA keys for multi-worker support",
    )

    # ===========================================
    # GOOGLE OAUTH SETTINGS
    # ===========================================

    # Google OAuth Client ID - required for Google Sign-In
    google_client_id: Optional[str] = Field(
        default=None,
        description="Google OAuth Client ID for verifying Google Sign-In tokens",
    )

    @property
    def google_oauth_enabled(self) -> bool:
        """Check if Google OAuth is configured and available."""
        return (
            self.google_client_id is not None and len(self.google_client_id.strip()) > 0
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

    # ===========================================
    # ENDPOINT HEALTH CHECK SETTINGS
    # ===========================================

    # Enable/disable periodic endpoint health monitoring
    health_check_enabled: bool = Field(
        default=True,
        description="Enable periodic endpoint health monitoring",
    )

    # Interval between health check cycles
    health_check_interval_seconds: int = Field(
        default=30,
        description="Interval between health check cycles in seconds",
    )

    # Timeout for individual health check requests
    health_check_timeout_seconds: float = Field(
        default=15.0,
        description="Timeout for individual health check requests in seconds",
    )

    # Number of consecutive failures before marking endpoint as unhealthy
    # This prevents transient network issues from causing false positive offline detections
    health_check_failure_threshold: int = Field(
        default=3,
        description="Number of consecutive health check failures before marking endpoint unhealthy",
    )

    # Maximum concurrent health check requests
    health_check_max_concurrent: int = Field(
        default=20,
        description="Maximum concurrent health check requests",
    )

    # ===========================================
    # HEARTBEAT SETTINGS (Deprecated)
    # ===========================================
    # These settings are used by the deprecated heartbeat endpoints
    # (POST /users/me/heartbeat, POST /organizations/{org_id}/heartbeat)
    # and also by POST /endpoints/health for TTL capping.
    #
    # When the deprecated heartbeat endpoints are removed, rename these
    # to generic TTL settings (e.g., health_max_ttl_seconds) or inline
    # them into the endpoint health configuration above.

    # Maximum TTL that clients can request for heartbeats
    # Set to 1800s (30 min) to match SyftAI-Space heartbeat manager's max TTL
    # (600s interval * 3 TTL multiplier = 1800s)
    heartbeat_max_ttl_seconds: int = Field(
        default=1800,
        description="Maximum TTL clients can request for heartbeats (30 min cap)",
    )

    # Default TTL if client doesn't specify
    heartbeat_default_ttl_seconds: int = Field(
        default=300,
        description="Default heartbeat TTL if not specified (5 min)",
    )

    # ===========================================
    # RAG / MEILISEARCH SETTINGS
    # ===========================================

    # Meilisearch server URL (e.g. http://meilisearch:7700)
    meili_url: Optional[str] = Field(
        default=None,
        description="Meilisearch server URL for endpoint search",
    )

    # Meilisearch master key (optional in dev, required in production)
    meili_master_key: Optional[str] = Field(
        default=None,
        description="Meilisearch master/API key",
    )

    # Meilisearch index name for endpoints
    meili_index_name: str = Field(
        default="syfthub-endpoints",
        description="Meilisearch index name for endpoint documents",
    )

    # Feature flag to enable/disable RAG functionality
    rag_enabled: bool = Field(
        default=True,
        description="Enable search indexing for endpoints",
    )

    # Maximum results to request from Meilisearch (before filtering)
    rag_max_results: int = Field(
        default=50,
        description="Maximum results to request from Meilisearch search",
    )

    @property
    def rag_available(self) -> bool:
        """Check if search functionality is available and configured."""
        return (
            self.rag_enabled
            and self.meili_url is not None
            and len(self.meili_url.strip()) > 0
        )

    # ===========================================
    # NATS SETTINGS
    # ===========================================

    # NATS server URL for internal service connections
    nats_url: str = Field(
        default="nats://nats:4222",
        description="NATS server URL for internal connections",
    )

    # NATS authentication token (shared secret)
    nats_auth_token: str = Field(
        default="",
        description="Authentication token for NATS server connections",
    )

    # Public WebSocket URL for NATS (used by external clients via nginx)
    nats_ws_public_url: str = Field(
        default="ws://localhost:8080/nats",
        description="Public WebSocket URL for NATS connections (via nginx proxy)",
    )

    # Peer token lifetime in seconds
    peer_token_expire_seconds: int = Field(
        default=120,
        description="Peer token lifetime in seconds (short-lived)",
    )

    # ===========================================
    # REDIS SETTINGS
    # ===========================================

    # Redis connection URL
    redis_url: str = Field(
        default="redis://localhost:6379/0",
        description="Redis connection URL",
    )

    # ===========================================
    # NGROK TUNNEL SETTINGS
    # ===========================================

    # API key for ngrok REST API (enables tunnel credentials endpoint)
    ngrok_api_key: Optional[str] = Field(
        default=None,
        description="API key for ngrok REST API (enables tunnel credentials)",
    )

    # Base domain for ngrok reserved tunnel domains
    # User domain = {username}.{ngrok_base_domain}
    ngrok_base_domain: str = Field(
        default="syfthub.ngrok.app",
        description="Base domain for ngrok reserved tunnel domains",
    )

    # ===========================================
    # LINEAR INTEGRATION (Feedback / Bug Reports)
    # ===========================================

    linear_api_key: Optional[str] = Field(
        default=None,
        description="Linear API key for creating feedback/bug report issues",
    )
    linear_team_id: Optional[str] = Field(
        default=None,
        description="Linear team ID to assign feedback issues to",
    )


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


settings = get_settings()
