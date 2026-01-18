"""Constants for observability layer."""

# HTTP header for correlation ID propagation
CORRELATION_ID_HEADER = "X-Correlation-ID"

# Service identifier for logs
SERVICE_NAME = "aggregator"


# Log event names following the pattern: {domain}.{action}.{result}
class LogEvents:
    """Standardized log event names."""

    # Chat events
    CHAT_REQUEST_STARTED = "chat.request.started"
    CHAT_REQUEST_COMPLETED = "chat.request.completed"
    CHAT_REQUEST_FAILED = "chat.request.failed"

    # Retrieval events
    CHAT_RETRIEVAL_STARTED = "chat.retrieval.started"
    CHAT_RETRIEVAL_COMPLETED = "chat.retrieval.completed"
    CHAT_RETRIEVAL_FAILED = "chat.retrieval.failed"
    CHAT_RETRIEVAL_TIMEOUT = "chat.retrieval.timeout"

    # Generation events
    CHAT_GENERATION_STARTED = "chat.generation.started"
    CHAT_GENERATION_COMPLETED = "chat.generation.completed"
    CHAT_GENERATION_FAILED = "chat.generation.failed"
    CHAT_GENERATION_TIMEOUT = "chat.generation.timeout"

    # SSE streaming events
    SSE_STREAM_STARTED = "sse.stream.started"
    SSE_STREAM_COMPLETED = "sse.stream.completed"
    SSE_STREAM_FAILED = "sse.stream.failed"
    SSE_CHUNK_SENT = "sse.chunk.sent"

    # Data source events
    DATA_SOURCE_QUERY_STARTED = "data_source.query.started"
    DATA_SOURCE_QUERY_COMPLETED = "data_source.query.completed"
    DATA_SOURCE_QUERY_FAILED = "data_source.query.failed"

    # Model events
    MODEL_QUERY_STARTED = "model.query.started"
    MODEL_QUERY_COMPLETED = "model.query.completed"
    MODEL_QUERY_FAILED = "model.query.failed"

    # Request lifecycle events
    REQUEST_STARTED = "request.started"
    REQUEST_COMPLETED = "request.completed"
    REQUEST_FAILED = "request.failed"

    # Error events
    ERROR_UNHANDLED = "error.unhandled"
    ERROR_VALIDATION = "error.validation"
    ERROR_UNAUTHORIZED = "error.unauthorized"


# Fields that should be redacted in logs
SENSITIVE_FIELDS = frozenset({
    # Authentication
    "password",
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
    # Chat content (may contain sensitive info)
    "system_prompt",
    # Keys
    "rsa_private_key",
    "encryption_key",
    "signing_key",
})

# Fields to redact (case-insensitive patterns)
SENSITIVE_FIELD_PATTERNS = frozenset({
    "password",
    "secret",
    "token",
    "key",
    "credential",
    "auth",
})

# Redaction placeholder
REDACTED_VALUE = "[REDACTED]"
