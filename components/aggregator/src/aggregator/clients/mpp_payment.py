"""Shared MPP (Micropayment Protocol) 402 payment flow handler.

When a Syft Space endpoint returns HTTP 402 Payment Required, this helper
extracts the WWW-Authenticate challenge, calls the SyftHub wallet to pay,
and returns an X-Payment credential that the caller can attach to a retry.
"""

from __future__ import annotations

import logging

import httpx

logger = logging.getLogger(__name__)


async def handle_mpp_payment(
    response: httpx.Response,
    syfthub_url: str,
    user_token: str,
    endpoint_slug: str,
    http_client: httpx.AsyncClient,
) -> str | None:
    """If *response* is 402, pay via the SyftHub wallet and return an X-Payment credential.

    Args:
        response: The upstream HTTP response (may or may not be 402).
        syfthub_url: Base URL of the SyftHub backend (e.g. ``http://localhost:8000``).
        user_token: The end-user's Hub JWT used to authorise the wallet payment.
        endpoint_slug: Slug of the endpoint being accessed (passed to the pay API).
        http_client: An ``httpx.AsyncClient`` to use for the outbound pay request.

    Returns:
        The ``x_payment`` credential string on success, or ``None`` if the
        response was not a 402 or the challenge header was missing.

    Raises:
        httpx.HTTPStatusError: If the pay request itself fails (non-2xx).
    """
    if response.status_code != 402:
        return None

    www_authenticate = response.headers.get("www-authenticate", "")
    if not www_authenticate:
        logger.warning(
            "Received 402 but no WWW-Authenticate header from endpoint %s",
            endpoint_slug,
        )
        return None

    logger.info(
        "Handling MPP 402 for endpoint %s – calling Hub wallet/pay",
        endpoint_slug,
    )

    pay_response = await http_client.post(
        f"{syfthub_url.rstrip('/')}/api/v1/wallet/pay",
        json={
            "www_authenticate": www_authenticate,
            "endpoint_slug": endpoint_slug,
        },
        headers={"Authorization": f"Bearer {user_token}"},
        timeout=30.0,
    )
    pay_response.raise_for_status()

    x_payment: str = pay_response.json()["x_payment"]
    logger.info("MPP payment successful for endpoint %s", endpoint_slug)
    return x_payment
