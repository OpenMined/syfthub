"""Constants for observability layer."""

# HTTP header for correlation ID propagation
CORRELATION_ID_HEADER = "X-Correlation-ID"

# Service identifier for logs
SERVICE_NAME = "backend"


# Log event names following the pattern: {domain}.{action}.{result}
class LogEvents:
    """Standardized log event names."""

    # Authentication events
    AUTH_LOGIN_SUCCESS = "auth.login.success"
    AUTH_LOGIN_FAILED = "auth.login.failed"
    AUTH_LOGOUT = "auth.logout"
    AUTH_TOKEN_REFRESH = "auth.token.refresh"
    AUTH_TOKEN_INVALID = "auth.token.invalid"

    # User events
    USER_CREATED = "user.created"
    USER_UPDATED = "user.updated"
    USER_DELETED = "user.deleted"

    # Endpoint events
    ENDPOINT_CREATED = "endpoint.created"
    ENDPOINT_UPDATED = "endpoint.updated"
    ENDPOINT_DELETED = "endpoint.deleted"
    ENDPOINT_INVOKED = "endpoint.invoked"
    ENDPOINT_INVOKE_FAILED = "endpoint.invoke.failed"

    # Request lifecycle events
    REQUEST_STARTED = "request.started"
    REQUEST_COMPLETED = "request.completed"
    REQUEST_FAILED = "request.failed"

    # Error events
    ERROR_UNHANDLED = "error.unhandled"
    ERROR_VALIDATION = "error.validation"
    ERROR_NOT_FOUND = "error.not_found"
    ERROR_UNAUTHORIZED = "error.unauthorized"
    ERROR_FORBIDDEN = "error.forbidden"

    # Health check events
    HEALTH_CHECK_SUCCESS = "health.check.success"
    HEALTH_CHECK_FAILED = "health.check.failed"


# Fields that should be redacted in logs
SENSITIVE_FIELDS = frozenset(
    {
        # Authentication
        "password",
        "new_password",
        "old_password",
        "current_password",
        "confirm_password",
        "secret",
        "secret_key",
        "private_key",
        # Tokens
        "token",
        "access_token",
        "refresh_token",
        "api_key",
        "apikey",
        "api_secret",
        "bearer",
        "authorization",
        "auth",
        # Financial/PII
        "credit_card",
        "card_number",
        "cvv",
        "ssn",
        "social_security",
        # Session
        "session_id",
        "session_token",
        "cookie",
        "csrf_token",
        # Keys
        "rsa_private_key",
        "rsa_private_key_pem",
        "encryption_key",
        "signing_key",
    }
)

# Fields to redact (case-insensitive patterns)
SENSITIVE_FIELD_PATTERNS = frozenset(
    {
        "password",
        "secret",
        "token",
        "key",
        "credential",
        "auth",
    }
)

# Redaction placeholder
REDACTED_VALUE = "[REDACTED]"
