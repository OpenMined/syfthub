#!/usr/bin/env python3
"""
Policy-enforced SyftHub Space — demonstrates every built-in policy type.

This example creates multiple endpoints, each showcasing a different policy
from the ``policy_manager`` package.  It also shows global policies, per-endpoint
policies, composite combinators, and a fully custom Policy subclass.

Policies shown:
    1. RateLimitPolicy   — global, applies to all endpoints
    2. TokenLimitPolicy  — caps input/output character counts
    3. AccessGroupPolicy — restricts access to specific users
    4. PromptFilterPolicy— blocks queries matching forbidden patterns
    5. ManualReviewPolicy— holds model responses for human review
    6. TransactionPolicy — ledger-based payment confirmation
    7. AttributionPolicy — requires a verified attribution URL
    8. CustomPolicy      — wraps a plain callable as a policy
    9. AllOf / AnyOf / Not — composite combinators
   10. Custom subclass   — full Policy subclass for business-hour gating

Required environment variables:
    SYFTHUB_URL      — URL of the SyftHub instance
    SYFTHUB_USERNAME — Your SyftHub username
    SYFTHUB_PASSWORD — Your SyftHub password
    SPACE_URL        — The public URL where this space is reachable

Usage:
    export SYFTHUB_URL="http://localhost:8080"
    export SYFTHUB_USERNAME="your-username"
    export SYFTHUB_PASSWORD="your-password"
    export SPACE_URL="http://localhost:8001"
    python examples/policies_server.py
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from policy_manager.context import RequestContext
from policy_manager.policies import (
    AccessGroupPolicy,
    AllOf,
    AttributionPolicy,
    CustomPolicy,
    ManualReviewPolicy,
    Policy,
    PromptFilterPolicy,
    RateLimitPolicy,
    TokenLimitPolicy,
    TransactionPolicy,
)
from policy_manager.result import PolicyResult

from syfthub_api import Document, Message, SyftAPI, UserContext

# ────────────────────────────────────────────────────────────────────
# Custom Policy subclass — only allow requests during business hours
# ────────────────────────────────────────────────────────────────────


class BusinessHoursPolicy(Policy):
    """Only allows requests between start_hour and end_hour (UTC)."""

    def __init__(
        self,
        *,
        name: str = "business_hours",
        start_hour: int = 9,
        end_hour: int = 17,
    ) -> None:
        self._name = name
        self.start_hour = start_hour
        self.end_hour = end_hour

    @property
    def name(self) -> str:
        return self._name

    async def pre_execute(self, context: RequestContext) -> PolicyResult:
        hour = datetime.now(timezone.utc).hour
        if self.start_hour <= hour < self.end_hour:
            return PolicyResult.allow(self.name)
        return PolicyResult.deny(
            self.name,
            f"Requests only allowed {self.start_hour}:00–{self.end_hour}:00 UTC "
            f"(current: {hour}:00 UTC)",
        )


# ────────────────────────────────────────────────────────────────────
# Instantiate reusable policy objects
# ────────────────────────────────────────────────────────────────────

# Global — every endpoint gets at most 60 requests per minute
global_rate_limit = RateLimitPolicy(
    name="global_rate_limit",
    max_requests=60,
    window_seconds=60,
)

# Per-endpoint instances
token_limit = TokenLimitPolicy(
    name="token_limit",
    max_input_tokens=500,
    max_output_tokens=2000,
)

access_group = AccessGroupPolicy(
    name="internal_team",
    users=["alice", "bob", "charlie", 'jr12'],
    documents=["doc-internal-1", "doc-internal-2"],
)

prompt_filter = PromptFilterPolicy(
    name="content_filter",
    patterns=[
        r"(?i)\b(password|secret|ssn)\b",         # block sensitive keywords
        r"\b\d{3}-\d{2}-\d{4}\b",                 # block SSN-like patterns
    ],
    check_input=True,
    check_output=True,
)

manual_review = ManualReviewPolicy(name="human_review")

transaction = TransactionPolicy(
    name="pay_per_query",
    price_per_request=1.0,  # Uses LEDGER_URL and LEDGER_API_TOKEN env vars
)

async def _verify_attribution(user_id: str, url: str) -> bool:
    """Simple check: any https:// URL counts as valid attribution."""
    return bool(url and url.startswith("https://"))


attribution = AttributionPolicy(
    name="citation_check",
    verify_callback=_verify_attribution,
)

business_hours = BusinessHoursPolicy(start_hour=6, end_hour=22)

# CustomPolicy — block queries shorter than 3 characters
min_length_check = CustomPolicy(
    name="min_query_length",
    phase="pre",
    check=lambda ctx: len(ctx.input.get("query", "")) >= 3,
    deny_reason="Query must be at least 3 characters long",
)

# ────────────────────────────────────────────────────────────────────
# Application
# ────────────────────────────────────────────────────────────────────

app = SyftAPI()

# Register the global rate limit — applies to every endpoint
app.add_policy(global_rate_limit)


# ── 1. Token-limited data source ────────────────────────────────────

@app.datasource(
    slug="token-limited-docs",
    name="Token-Limited Docs",
    description="Data source with input/output character limits (TokenLimitPolicy).",
    policies=[token_limit],
)
async def token_limited_search(query: str) -> list[Document]:
    """Queries longer than 500 chars or responses longer than 2000 chars are denied."""
    return [
        Document(
            document_id="tl-1",
            content=f"Token-limited result for: {query}",
            similarity_score=0.95,
        ),
    ]


# ── 2. Access-group restricted data source ──────────────────────────

@app.datasource(
    slug="internal-docs",
    name="Internal Documents",
    description="Only accessible by members of the 'internal_team' access group.",
    policies=[access_group],
)
async def internal_search(query: str, user: UserContext) -> list[Document]:
    """Only alice, bob, and charlie can query this endpoint."""
    return [
        Document(
            document_id="int-1",
            content=f"Internal doc for {user.username}: {query}",
            metadata={"classification": "internal"},
            similarity_score=0.92,
        ),
    ]


# ── 3. Content-filtered data source ────────────────────────────────

@app.datasource(
    slug="filtered-docs",
    name="Filtered Documents",
    description="Blocks queries/responses containing sensitive patterns (PromptFilterPolicy).",
    policies=[prompt_filter],
)
async def filtered_search(query: str) -> list[Document]:
    """Queries with 'password', 'secret', 'ssn', or SSN patterns are blocked."""
    return [
        Document(
            document_id="f-1",
            content=f"Filtered result for: {query}",
            similarity_score=0.88,
        ),
    ]


# ── 4. Manually-reviewed model ─────────────────────────────────────

@app.model(
    slug="reviewed-model",
    name="Reviewed Model",
    description="Responses are held for human review before delivery (ManualReviewPolicy).",
    policies=[manual_review],
)
async def reviewed_model(messages: list[Message]) -> str:
    """Every response goes through manual review (returns 'pending')."""
    last = next((m.content for m in reversed(messages) if m.role == "user"), "")
    return f"Pending review — answer to: {last}"


# ── 5. Ledger-gated model ──────────────────────────────────────────

@app.model(
    slug="paid-model",
    name="Paid Model",
    description="Costs $1.00 per request (TransactionPolicy with Unified Ledger).",
    policies=[transaction],
)
async def paid_model(messages: list[Message], ctx: RequestContext) -> str:
    """Each call costs $1.00. Requires transaction_token from SDK pre-authorization."""
    last = next((m.content for m in reversed(messages) if m.role == "user"), "")
    confirmed = ctx.metadata.get("pay_per_query_confirmed", False)
    status = "confirmed" if confirmed else "pending"
    return f"Paid response (transaction {status}): {last}"


# ── 6. Attribution-required model ───────────────────────────────────

@app.model(
    slug="attributed-model",
    name="Attributed Model",
    description="Requires a verified https:// attribution URL (AttributionPolicy).",
    policies=[attribution],
)
async def attributed_model(messages: list[Message]) -> str:
    """Denied unless the request includes a valid attribution_url in the input context."""
    last = next((m.content for m in reversed(messages) if m.role == "user"), "")
    return f"Attributed response: {last}"


# ── 7. Custom callable policy ──────────────────────────────────────

@app.datasource(
    slug="min-length-docs",
    name="Min-Length Docs",
    description="Rejects queries shorter than 3 characters (CustomPolicy).",
    policies=[min_length_check],
)
async def min_length_search(query: str) -> list[Document]:
    """Try querying with 'ab' — it will be denied."""
    return [
        Document(
            document_id="ml-1",
            content=f"Result for: {query}",
            similarity_score=0.90,
        ),
    ]


# ── 8. Custom Policy subclass (business hours) ─────────────────────

@app.model(
    slug="office-hours-model",
    name="Office Hours Model",
    description="Only available 06:00–22:00 UTC (custom BusinessHoursPolicy subclass).",
    policies=[business_hours],
)
async def office_hours_model(messages: list[Message]) -> str:
    """Denied outside of the configured UTC hour window."""
    last = next((m.content for m in reversed(messages) if m.role == "user"), "")
    return f"Office hours response: {last}"


# ── 9. Composite policy — AllOf ─────────────────────────────────────

@app.model(
    slug="premium-model",
    name="Premium Model",
    description="Requires ALL of: access group membership, token limit, and business hours.",
    policies=[
        AllOf(
            AccessGroupPolicy(
                name="premium_users",
                users=["alice", "bob"],
            ),
            TokenLimitPolicy(
                name="premium_token_limit",
                max_input_tokens=1000,
                max_output_tokens=5000,
            ),
            BusinessHoursPolicy(name="premium_hours", start_hour=8, end_hour=20),
            name="premium_gate",
        ),
    ],
)
async def premium_model(
    messages: list[Message],
    user: UserContext,
    ctx: RequestContext,
) -> str:
    """Only premium users, within token limits, during business hours."""
    last = next((m.content for m in reversed(messages) if m.role == "user"), "")
    return f"Premium response for {user.username}: {last}"


# ────────────────────────────────────────────────────────────────────
# Lifecycle hooks
# ────────────────────────────────────────────────────────────────────

@app.on_startup
async def check_ledger_config():
    """Check that ledger is configured for the paid-model endpoint."""
    import os

    ledger_url = os.getenv("LEDGER_URL")
    has_token = bool(os.getenv("LEDGER_API_TOKEN"))

    if ledger_url and has_token:
        print(f"Ledger configured: {ledger_url}")
    else:
        print("WARNING: LEDGER_URL or LEDGER_API_TOKEN not set.")
        print("The 'paid-model' endpoint requires ledger configuration.")
        print("Transactions will fail without valid ledger credentials.")


@app.on_startup
async def startup_banner():
    print("Policy-enforced space is online.")
    print("Endpoints registered:")
    for ep in app.endpoints:
        policy_names = [p.name for p in ep.get("_resolved_policies", ep.get("policies", []))]
        print(f"  [{ep['type'].value}] /{ep['slug']}  policies={policy_names}")


# ────────────────────────────────────────────────────────────────────
# Main
# ────────────────────────────────────────────────────────────────────

async def main() -> None:
    await app.run(host="0.0.0.0", port=8001)


if __name__ == "__main__":
    asyncio.run(main())
