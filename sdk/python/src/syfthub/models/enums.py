"""String enums. Values are the Hub's and the Space's wire values, unchanged."""

from __future__ import annotations

from enum import StrEnum


class SourceType(StrEnum):
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


class Rail(StrEnum):
    """How a source is paid; read off its payment policy."""

    FREE = "free"
    STRIPE = "stripe"
    XENDIT = "xendit"
    CLUSTER = "cluster"
    MPP = "mpp"

    @property
    def prepaid(self) -> bool:
        return self in (Rail.STRIPE, Rail.XENDIT, Rail.CLUSTER)


class PolicyType(StrEnum):
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


class PriceUnit(StrEnum):
    REQUEST = "request"
    DOCUMENT = "document"


class AuthMethod(StrEnum):
    PASSWORD = "password"
    TOKEN = "token"
    GOOGLE = "google"


class Verdict(StrEnum):
    """Pre-flight, per row. The first two are sent; the rest are held."""

    READY = "ready"
    WILL_ASK_TO_PAY = "will_ask_to_pay"
    NEEDS_CREDITS = "needs_credits"
    OVER_BUDGET = "over_budget"
    ACCESS_DENIED = "access_denied"
    CIRCUIT_OPEN = "circuit_open"
    UNREACHABLE = "unreachable"
    SKIPPED = "skipped"

    @property
    def sends(self) -> bool:
        return self in (Verdict.READY, Verdict.WILL_ASK_TO_PAY)


class ActionKind(StrEnum):
    TOP_UP = "top_up"
    OVER_BUDGET = "over_budget"
    ACCESS_DENIED = "access_denied"
    CIRCUIT_OPEN = "circuit_open"


class Outcome(StrEnum):
    """Execute, per row."""

    RETURNED = "returned"
    HELD = "held"
    REJECTED = "rejected"
    FAILED = "failed"
    PAYMENT_REQUIRED = "payment_required"


class Reason(StrEnum):
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


class ReturnKind(StrEnum):
    REFERENCES = "references"
    SUMMARIES = "summaries"
    BOTH = "both"
    NOTHING = "nothing"


class InvoiceStatus(StrEnum):
    """The Space's invoice lifecycle: pending -> (processing ->) paid, or expired / cancelled."""

    PENDING = "pending"
    PROCESSING = "processing"
    PAID = "paid"
    EXPIRED = "expired"
    CANCELLED = "cancelled"

    @property
    def open(self) -> bool:
        return self in (InvoiceStatus.PENDING, InvoiceStatus.PROCESSING)
