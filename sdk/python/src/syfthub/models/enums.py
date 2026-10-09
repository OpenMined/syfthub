"""String enums. Values are the Hub's and the Space's wire values, unchanged."""

from __future__ import annotations

from enum import Enum


class SourceType(str, Enum):
    """What a source answers with. Values are the Hub's endpoint types."""

    DOCUMENTS = "data_source"
    MODEL = "model"
    BOTH = "model_data_source"

    @property
    def returns_documents(self) -> bool:
        return self in (SourceType.DOCUMENTS, SourceType.BOTH)

    @property
    def returns_summary(self) -> bool:
        return self in (SourceType.MODEL, SourceType.BOTH)


class Rail(str, Enum):
    """How a source is paid; read off its payment policy."""

    FREE = "free"
    STRIPE = "stripe"
    XENDIT = "xendit"
    CLUSTER = "cluster"
    MPP = "mpp"

    @property
    def prepaid(self) -> bool:
        return self in (Rail.STRIPE, Rail.XENDIT, Rail.CLUSTER)


class PolicyType(str, Enum):
    """Policy types the SDK knows. ``Policy.type`` stays a string so unknown types still parse."""

    STRIPE = "stripe"
    XENDIT = "xendit"
    CLUSTER = "cluster"
    MPP = "mpp"
    ACCESS = "access"
    RATE_LIMIT = "rate_limit"
    PII_FILTER = "pii_filter"


PAYMENT_POLICY_TYPES: frozenset[str] = frozenset(
    {PolicyType.STRIPE, PolicyType.XENDIT, PolicyType.CLUSTER, PolicyType.MPP}
)


class PriceUnit(str, Enum):
    REQUEST = "request"
    DOCUMENT = "document"


class Health(str, Enum):
    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


class AuthMethod(str, Enum):
    PASSWORD = "password"
    TOKEN = "token"
    GOOGLE = "google"


class Verdict(str, Enum):
    """Pre-flight, per row. The first three are sent; the rest are held."""

    READY = "ready"
    WILL_ASK_TO_PAY = "will_ask_to_pay"
    UNHEALTHY = "unhealthy"
    NEEDS_CREDITS = "needs_credits"
    OVER_BUDGET = "over_budget"
    ACCESS_DENIED = "access_denied"
    CIRCUIT_OPEN = "circuit_open"
    SKIPPED = "skipped"

    @property
    def sends(self) -> bool:
        return self in (Verdict.READY, Verdict.WILL_ASK_TO_PAY, Verdict.UNHEALTHY)


class ActionKind(str, Enum):
    TOP_UP = "top_up"
    OVER_BUDGET = "over_budget"
    ACCESS_DENIED = "access_denied"
    CIRCUIT_OPEN = "circuit_open"


class Outcome(str, Enum):
    """Execute, per row."""

    RETURNED = "returned"
    HELD = "held"
    REJECTED = "rejected"
    FAILED = "failed"
    PAYMENT_REQUIRED = "payment_required"


class Reason(str, Enum):
    NO_CREDITS = "no_credits"
    OVER_BUDGET = "over_budget"
    ACCESS_DENIED = "access_denied"
    CIRCUIT_OPEN = "circuit_open"
    BY_USER = "by_user"
    RATE_LIMITED = "rate_limited"
    NO_PRICING_TIER = "no_pricing_tier"
    BLOCKED = "blocked"
    UNREACHABLE = "unreachable"
    TIMEOUT = "timeout"
    SERVER_ERROR = "server_error"
    NOT_FOUND = "not_found"
    NOT_PUBLISHED = "not_published"
    AUTH = "auth"


class ReturnKind(str, Enum):
    REFERENCES = "references"
    SUMMARIES = "summaries"
    BOTH = "both"
    NOTHING = "nothing"


class InvoiceStatus(str, Enum):
    """The Space's invoice lifecycle: pending -> (processing ->) paid, or expired / cancelled."""

    PENDING = "pending"
    PROCESSING = "processing"
    PAID = "paid"
    EXPIRED = "expired"
    CANCELLED = "cancelled"

    @property
    def open(self) -> bool:
        return self in (InvoiceStatus.PENDING, InvoiceStatus.PROCESSING)
