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
