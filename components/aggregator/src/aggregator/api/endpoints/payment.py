"""Chat-payment submission endpoint.

The chat client receives a ``payment_required`` SSE event from an in-flight
chat stream, signs and submits the on-chain payment via its wallet, then POSTs
the resulting credential here. The route resolves the awaiting future inside
the process-singleton ``PaymentNegotiator`` so the suspended tunnel call
can retry with the credential attached.
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from aggregator.api.dependencies import get_payment_negotiator
from aggregator.clients import PaymentNegotiator

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["chat"])


class PaymentSubmission(BaseModel):
    """Body for ``POST /chat/{session_id}/payment``."""

    challenge_id: str = Field(
        ...,
        description="The challenge_id from the corresponding payment_required SSE event.",
    )
    credential: str = Field(
        ...,
        description=(
            "The X-Payment credential string to attach when retrying the tunneled "
            "endpoint call (typically 'Payment <base64-jwt>')."
        ),
    )


class PaymentSubmissionResponse(BaseModel):
    """Response for an accepted payment submission."""

    status: str = Field(default="accepted", description="Always 'accepted' on 200.")


@router.post(
    "/{session_id}/payment",
    response_model=PaymentSubmissionResponse,
    responses={
        404: {"description": "No pending payment matches the (session_id, challenge_id) pair."},
    },
)
async def submit_payment(
    session_id: str,
    body: PaymentSubmission,
    negotiator: Annotated[PaymentNegotiator, Depends(get_payment_negotiator)],
) -> PaymentSubmissionResponse:
    """Submit a payment credential for a pending payment_required negotiation.

    The negotiator resolves the awaiting future, the suspended tunnel call
    retries with the credential attached, and the chat stream resumes.
    """
    matched = negotiator.submit_credential(session_id, body.challenge_id, body.credential)
    if not matched:
        raise HTTPException(
            status_code=404,
            detail=(
                f"No pending payment for challenge_id={body.challenge_id} "
                f"in session_id={session_id}"
            ),
        )
    return PaymentSubmissionResponse(status="accepted")
