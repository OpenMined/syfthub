"""Shared helper for extracting policy_metadata from upstream responses."""

from __future__ import annotations

from typing import Any

import httpx


def extract_policy_metadata(response: httpx.Response) -> dict[str, Any] | None:
    """Extract the policy_metadata object from a response body (success or error).

    Returns the ``policy_metadata`` dict if the response body is JSON and contains
    a dict-valued ``policy_metadata`` key, otherwise None. Never raises.
    """
    try:
        data = response.json()
    except Exception:
        return None
    if isinstance(data, dict):
        policy_metadata = data.get("policy_metadata")
        if isinstance(policy_metadata, dict):
            return policy_metadata
    return None


# Producer rejection outcomes that map 1:1 to a precise per-source status.
# (success / payment_required are deliberately excluded — success isn't a
# failure, and a 402 is reported as the aggregator-side "payment_failed".)
_OUTCOME_TO_SOURCE_STATUS = {
    "access_denied": "access_denied",
    "rate_limited": "rate_limited",
    "policy_violation": "policy_violation",
}


def source_status_from_policy_metadata(
    policy_metadata: dict[str, Any] | None,
) -> str | None:
    """Derive a precise per-source status from a rejection's ``outcome``.

    The HTTP status alone is coarse — any policy block is a 403. When the body
    carries policy_metadata, its ``outcome`` distinguishes ``access_denied`` vs
    ``rate_limited`` vs a generic ``policy_violation``. Returns None when the
    outcome doesn't map, so the caller falls back to its default status.
    """
    if not policy_metadata:
        return None
    outcome = policy_metadata.get("outcome")
    if not isinstance(outcome, str):
        return None
    return _OUTCOME_TO_SOURCE_STATUS.get(outcome)
