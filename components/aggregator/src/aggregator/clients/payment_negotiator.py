"""Passthrough payment negotiator for on-chain Tempo payments via MPP-over-NATS.

When a tunneling Syft Space returns a tunnel response with
``status == "error"`` and ``error.code == "PAYMENT_REQUIRED"``, the aggregator
must:

1. Surface the challenge to the chat client as an SSE ``payment_required`` event.
2. Wait for the client to POST a credential to ``/chat/{session_id}/payment``.
3. Replay the original tunnel call with the credential attached.

The aggregator does **not** hold a wallet. It is a passthrough negotiator —
the client's wallet (or the user, via the desktop app) signs and submits the
payment, and the aggregator only relays the resulting credential.

Idempotency
-----------
Responses are cached per ``challenge_id`` for 10 minutes so client reconnects
or duplicate retries do not double-charge the user. The cache is in-memory and
process-local; horizontal scaling would require an external store.

Multi-endpoint chats
--------------------
For a chat that fans out to K endpoints, K independent ``execute_with_payment``
calls run concurrently, each emitting its own ``payment_required`` event keyed
by ``challenge_id`` and ``endpoint_slug``. The aggregator does not bundle them;
the client UI is responsible for collecting and presenting the bundle.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


# Default tunnel-response error code for the MPP payment-required signal.
PAYMENT_REQUIRED_ERROR_CODE = "PAYMENT_REQUIRED"

# Idempotency cache defaults.
DEFAULT_TTL_SECONDS = 600  # 10 minutes
DEFAULT_MAX_PENDING = 10000

# Default time we will wait for a client to submit a credential.
DEFAULT_CREDENTIAL_TIMEOUT_SECONDS = 300.0


@dataclass(frozen=True)
class PaymentChallenge:
    """A payment challenge extracted from a tunnel PAYMENT_REQUIRED response."""

    challenge_id: str
    challenge: str  # Raw WWW-Authenticate-style challenge string
    amount: str
    currency: str
    recipient: str
    intent: str
    endpoint_slug: str


def _is_payment_required(response: Any) -> bool:
    """Return True if a TunnelResponse-like dict signals PAYMENT_REQUIRED.

    The expected shape (from the Go-SDK side, units 1+2+4 of the parallel batch)::

        {
            "status": "error",
            "error": {
                "code": "PAYMENT_REQUIRED",
                "details": {
                    "payment_challenge": "...",
                    "payment_amount": "...",
                    "payment_currency": "...",
                    "payment_recipient": "...",
                    "challenge_id": "...",
                    "intent": "charge",
                },
            },
        }
    """
    if not isinstance(response, dict):
        return False
    if response.get("status") != "error":
        return False
    error = response.get("error")
    if not isinstance(error, dict):
        return False
    return error.get("code") == PAYMENT_REQUIRED_ERROR_CODE


def _extract_challenge(response: Any, *, endpoint_slug: str) -> PaymentChallenge:
    """Extract a PaymentChallenge from a PAYMENT_REQUIRED tunnel response.

    Raises:
        ValueError: If the response does not contain the required fields.
    """
    if not isinstance(response, dict):
        raise ValueError("Response is not a dict")
    error = response.get("error") or {}
    details = error.get("details") or {}
    if not isinstance(details, dict):
        raise ValueError("error.details is not a dict")

    challenge_id = details.get("challenge_id")
    if not challenge_id:
        raise ValueError("error.details.challenge_id missing")

    return PaymentChallenge(
        challenge_id=str(challenge_id),
        challenge=str(details.get("payment_challenge", "")),
        amount=str(details.get("payment_amount", "")),
        currency=str(details.get("payment_currency", "")),
        recipient=str(details.get("payment_recipient", "")),
        intent=str(details.get("intent", "charge")),
        endpoint_slug=endpoint_slug,
    )


class PaymentNegotiator:
    """Passthrough payment negotiator with in-memory idempotency cache.

    Single instance per process (wired onto ``app.state.payment_negotiator``).
    Safe to use from multiple concurrent chat sessions because each negotiation
    is keyed by ``(chat_session_id, challenge_id)``.
    """

    def __init__(
        self,
        *,
        ttl_seconds: int = DEFAULT_TTL_SECONDS,
        max_pending: int = DEFAULT_MAX_PENDING,
    ) -> None:
        # Pending negotiations: (chat_session_id, challenge_id) -> Future awaiting credential.
        self._pending: dict[tuple[str, str], asyncio.Future[str]] = {}
        # Idempotency cache: challenge_id -> (response, expires_at_unix).
        self._cache: dict[str, tuple[Any, float]] = {}
        self._ttl = ttl_seconds
        self._max_pending = max_pending

    async def execute_with_payment(
        self,
        *,
        chat_session_id: str,
        endpoint_slug: str,
        tunnel_call: Callable[[str | None], Awaitable[Any]],
        emit_event: Callable[[dict[str, Any]], Awaitable[None]],
        timeout_seconds: float = DEFAULT_CREDENTIAL_TIMEOUT_SECONDS,
    ) -> Any:
        """Execute a tunnel call, transparently handling a PAYMENT_REQUIRED challenge.

        Args:
            chat_session_id: Chat session identifier (used to key pending futures).
            endpoint_slug: Slug of the endpoint being called (surfaced in the SSE event).
            tunnel_call: Async callable that performs the tunnel request. It is invoked
                first with ``None`` (no credential) and again with the client-provided
                credential string after the SSE round-trip. Must return a TunnelResponse-
                like dict.
            emit_event: Async callable that emits an SSE event payload to the chat
                client. The payload is a dict with keys ``event`` and ``data``.
            timeout_seconds: How long to wait for the client to submit a credential
                before raising ``asyncio.TimeoutError``.

        Returns:
            The final tunnel response (either the first response if no payment was
            required, or the post-credential response).
        """
        # First attempt without credential.
        response = await tunnel_call(None)
        if not _is_payment_required(response):
            return response

        challenge = _extract_challenge(response, endpoint_slug=endpoint_slug)

        # Idempotency: if this challenge_id was already paid for, return the cached response.
        cached = self._lookup_cache(challenge.challenge_id)
        if cached is not None:
            logger.info(
                "Reusing cached response for challenge_id=%s (idempotent retry)",
                challenge.challenge_id,
            )
            return cached

        # Surface the challenge to the chat client.
        await emit_event(
            {
                "event": "payment_required",
                "data": {
                    "chat_session_id": chat_session_id,
                    "endpoint_slug": challenge.endpoint_slug,
                    "challenge": challenge.challenge,
                    "amount": challenge.amount,
                    "currency": challenge.currency,
                    "recipient": challenge.recipient,
                    "challenge_id": challenge.challenge_id,
                    "intent": challenge.intent,
                },
            }
        )

        # Await the client credential.
        loop = asyncio.get_running_loop()
        future: asyncio.Future[str] = loop.create_future()
        key = (chat_session_id, challenge.challenge_id)
        # Refuse to negotiate when we are already at the pending-future cap. This
        # bounds memory under runaway clients; legitimate flows resolve quickly.
        if len(self._pending) >= self._max_pending:
            raise RuntimeError(
                f"PaymentNegotiator pending-future cap reached ({self._max_pending}); "
                "refusing new negotiation"
            )
        self._pending[key] = future

        try:
            credential = await asyncio.wait_for(future, timeout=timeout_seconds)
        finally:
            self._pending.pop(key, None)

        # Retry the tunnel call with the credential attached.
        retry_response = await tunnel_call(credential)
        # Cache the response keyed by challenge_id for the TTL window.
        self._store_cache(challenge.challenge_id, retry_response)
        return retry_response

    def submit_credential(self, chat_session_id: str, challenge_id: str, credential: str) -> bool:
        """Resolve the awaiting future for a pending negotiation.

        Returns:
            True if a matching pending negotiation was found and resolved,
            False otherwise (caller should respond 404).
        """
        key = (chat_session_id, challenge_id)
        future = self._pending.get(key)
        if future is None or future.done():
            return False
        future.set_result(credential)
        return True

    def _lookup_cache(self, challenge_id: str) -> Any | None:
        entry = self._cache.get(challenge_id)
        if entry is None:
            return None
        response, expires_at = entry
        if time.time() > expires_at:
            self._cache.pop(challenge_id, None)
            return None
        return response

    def _store_cache(self, challenge_id: str, response: Any) -> None:
        self._cache[challenge_id] = (response, time.time() + self._ttl)
        # Lazy eviction when the cache grows too large.
        if len(self._cache) > 2 * self._max_pending:
            now = time.time()
            self._cache = {k: v for k, v in self._cache.items() if v[1] > now}
