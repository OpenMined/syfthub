"""Accounting proxy endpoints for Unified Global Ledger.

These endpoints proxy requests to the Unified Global Ledger service,
avoiding CORS issues by making server-to-server calls.

The frontend calls these endpoints instead of the ledger service directly.

Migration from old accounting system:
- Uses Bearer token auth (API tokens) instead of Basic Auth
- Uses account IDs instead of email-based accounts
- Transfer confirmation flow replaces transaction tokens
"""

import logging
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from syfthub.auth.db_dependencies import get_current_active_user
from syfthub.database.dependencies import get_user_repository
from syfthub.repositories.user import UserRepository
from syfthub.schemas.user import User
from syfthub.services.unified_ledger_client import (
    LedgerBalance,
    LedgerTransfer,
    UnifiedLedgerClient,
)

logger = logging.getLogger(__name__)

router = APIRouter()


# =============================================================================
# Response Models
# =============================================================================


class AccountingUserResponse(BaseModel):
    """Accounting user info response (balance from Unified Ledger)."""

    id: str = Field(..., description="Account ID in the ledger")
    email: str = Field(..., description="User's email address")
    balance: float = Field(..., description="Available balance in credits")
    currency: str = Field(default="CREDIT", description="Currency code")


class TransferResponse(BaseModel):
    """Transfer response from the Unified Ledger."""

    id: str = Field(..., description="Transfer ID")
    source_account_id: str = Field(..., description="Source account ID")
    destination_account_id: str = Field(..., description="Destination account ID")
    amount: str = Field(..., description="Transfer amount")
    currency: str = Field(default="CREDIT", description="Currency code")
    status: str = Field(..., description="Transfer status")
    confirmation_token: Optional[str] = Field(
        None, description="Token for confirming pending transfers"
    )
    description: Optional[str] = Field(None, description="Transfer description")
    created_at: Optional[str] = Field(None, description="When the transfer was created")


class CreateTransferRequest(BaseModel):
    """Request to create a transfer."""

    destination_account_id: str = Field(..., description="Destination account ID")
    amount: str = Field(..., description="Amount to transfer")
    description: Optional[str] = Field(None, description="Transfer description")
    require_confirmation: bool = Field(
        default=False,
        description="If true, creates a pending transfer that requires confirmation",
    )


class OwnerAmountRequest(BaseModel):
    """Per-owner amount for transaction token creation."""

    owner_username: str = Field(..., description="Endpoint owner username")
    amount: str = Field(..., description="Amount to pre-authorize for this owner")


class CreateTransactionTokensRequest(BaseModel):
    """Request to create transaction tokens (confirmation tokens) for endpoint owners.

    Used by the chat flow to pre-authorize payments to endpoint owners.
    Each owner can have a different amount based on their endpoint's pricing policy.
    This creates pending transfers that the endpoint owners can confirm.
    """

    requests: list[OwnerAmountRequest] = Field(
        ...,
        description="List of owner/amount pairs for token creation",
        min_length=1,
        max_length=20,
    )


class TokenInfo(BaseModel):
    """Token information including the confirmation token and amount."""

    token: str = Field(..., description="Confirmation token for the pending transfer")
    amount: str = Field(..., description="Amount pre-authorized in this transfer")
    transfer_id: str = Field(..., description="Transfer ID (for cancellation)")


class TransactionTokensResponse(BaseModel):
    """Response containing confirmation tokens for endpoint owners.

    Maps owner_username to their token info (token + amount).
    The endpoint can verify the amount matches their pricing before confirming.
    """

    tokens: dict[str, TokenInfo] = Field(
        default_factory=dict,
        description="Mapping of owner_username to token info (token, amount, transfer_id)",
    )
    errors: dict[str, str] = Field(
        default_factory=dict,
        description="Mapping of owner_username to error message (if creation failed)",
    )


class ConfirmTransferRequest(BaseModel):
    """Request to confirm a pending transfer."""

    confirmation_token: str = Field(..., description="The confirmation token")


# =============================================================================
# Helper Functions
# =============================================================================


def get_ledger_client(user: User) -> UnifiedLedgerClient:
    """Get a ledger client configured with user's credentials.

    Args:
        user: The current user with accounting credentials

    Returns:
        UnifiedLedgerClient configured for the user

    Raises:
        HTTPException: If accounting is not configured for the user
    """
    if not user.accounting_service_url or not user.accounting_api_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Accounting not configured. Please set up billing in settings.",
        )
    if not user.accounting_account_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No accounting account linked. Please complete billing setup.",
        )
    return UnifiedLedgerClient(
        base_url=user.accounting_service_url,
        api_token=user.accounting_api_token,
    )


# =============================================================================
# Endpoints
# =============================================================================


@router.get("/user", response_model=AccountingUserResponse)
async def get_accounting_user(
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> AccountingUserResponse:
    """Get current user's accounting info including balance.

    Fetches the balance from the Unified Global Ledger using
    the user's linked account.
    """
    client = get_ledger_client(current_user)

    try:
        result = client.get_balance(current_user.accounting_account_id)  # type: ignore

        if not result.success:
            if result.status_code == 401:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid accounting credentials. Please reconfigure billing.",
                )
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=result.error or "Failed to fetch balance",
            )

        balance_data: LedgerBalance = result.data  # type: ignore[assignment]
        return AccountingUserResponse(
            id=current_user.accounting_account_id,  # type: ignore[arg-type]
            email=current_user.email,
            balance=float(balance_data.available_balance),
            currency=balance_data.currency,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Error communicating with ledger service: {e!s}",
        ) from e
    finally:
        client.close()


@router.post("/transfers", response_model=TransferResponse)
async def create_transfer(
    request: CreateTransferRequest,
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> TransferResponse:
    """Create a transfer to another account.

    If require_confirmation=True, creates a pending transfer that the
    recipient must confirm. The response will include a confirmation_token.
    """
    client = get_ledger_client(current_user)

    try:
        result = client.create_transfer(
            source_account_id=current_user.accounting_account_id,  # type: ignore
            destination_account_id=request.destination_account_id,
            amount=request.amount,
            description=request.description,
            require_confirmation=request.require_confirmation,
        )

        if not result.success:
            if result.status_code == 422:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=result.error or "Insufficient funds",
                )
            raise HTTPException(
                status_code=result.status_code or status.HTTP_502_BAD_GATEWAY,
                detail=result.error or "Failed to create transfer",
            )

        transfer: LedgerTransfer = result.data  # type: ignore[assignment]
        return TransferResponse(
            id=transfer.id,
            source_account_id=transfer.source_account_id,
            destination_account_id=transfer.destination_account_id,
            amount=transfer.amount,
            currency=transfer.currency,
            status=transfer.status,
            confirmation_token=transfer.confirmation_token,
            description=transfer.description,
            created_at=transfer.created_at,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Error communicating with ledger service: {e!s}",
        ) from e
    finally:
        client.close()


@router.post("/transfers/confirm", response_model=TransferResponse)
async def confirm_transfer(
    request: ConfirmTransferRequest,
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> TransferResponse:
    """Confirm a pending transfer using its confirmation token.

    This endpoint is typically called by the recipient (or their agent)
    to complete a transfer that was created with require_confirmation=True.
    """
    client = get_ledger_client(current_user)

    try:
        result = client.confirm_transfer(request.confirmation_token)

        if not result.success:
            raise HTTPException(
                status_code=result.status_code or status.HTTP_400_BAD_REQUEST,
                detail=result.error or "Failed to confirm transfer",
            )

        transfer: LedgerTransfer = result.data  # type: ignore[assignment]
        return TransferResponse(
            id=transfer.id,
            source_account_id=transfer.source_account_id,
            destination_account_id=transfer.destination_account_id,
            amount=transfer.amount,
            currency=transfer.currency,
            status=transfer.status,
            confirmation_token=None,  # Confirmed transfers don't have tokens
            description=transfer.description,
            created_at=transfer.created_at,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Error communicating with ledger service: {e!s}",
        ) from e
    finally:
        client.close()


@router.post("/transfers/{transfer_id}/cancel", response_model=TransferResponse)
async def cancel_transfer(
    transfer_id: str,
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> TransferResponse:
    """Cancel a pending transfer.

    Only the sender can cancel a pending transfer. This releases the
    held funds back to the sender's available balance.
    """
    client = get_ledger_client(current_user)

    try:
        result = client.cancel_transfer(transfer_id)

        if not result.success:
            raise HTTPException(
                status_code=result.status_code or status.HTTP_400_BAD_REQUEST,
                detail=result.error or "Failed to cancel transfer",
            )

        transfer: LedgerTransfer = result.data  # type: ignore[assignment]
        return TransferResponse(
            id=transfer.id,
            source_account_id=transfer.source_account_id,
            destination_account_id=transfer.destination_account_id,
            amount=transfer.amount,
            currency=transfer.currency,
            status=transfer.status,
            confirmation_token=None,  # Cancelled transfers don't have tokens
            description=transfer.description,
            created_at=transfer.created_at,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Error communicating with ledger service: {e!s}",
        ) from e
    finally:
        client.close()


@router.post("/transaction-tokens", response_model=TransactionTokensResponse)
async def create_transaction_tokens(
    request: CreateTransactionTokensRequest,
    current_user: Annotated[User, Depends(get_current_active_user)],
    user_repo: Annotated[UserRepository, Depends(get_user_repository)],
) -> TransactionTokensResponse:
    """Create confirmation tokens for multiple endpoint owners.

    This endpoint is used by the chat flow to pre-authorize payments to
    endpoint owners before making requests to their endpoints.

    Each owner can have a different amount based on their endpoint's pricing.
    The amount is extracted from the endpoint's TransactionPolicy by the SDK.

    For each owner/amount pair:
    1. Looks up the owner's accounting account ID from the database
    2. Creates a pending transfer to the owner's account for the specified amount
    3. Returns the token info (token + amount) for each owner

    The endpoint can verify the amount matches their pricing before confirming.

    Args:
        request: List of owner/amount pairs for token creation
        current_user: The authenticated user (will be charged)
        user_repo: Repository for looking up user accounts

    Returns:
        TransactionTokensResponse with token info and any errors
    """
    # Check if current user has accounting configured
    if not current_user.accounting_service_url or not current_user.accounting_api_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Accounting not configured. Please set up billing in settings.",
        )
    if not current_user.accounting_account_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No accounting account linked. Please complete billing setup.",
        )

    client = UnifiedLedgerClient(
        base_url=current_user.accounting_service_url,
        api_token=current_user.accounting_api_token,
    )

    tokens: dict[str, TokenInfo] = {}
    errors: dict[str, str] = {}

    try:
        for req in request.requests:
            owner_username = req.owner_username
            amount = req.amount

            # Skip if we've already processed this username (handle duplicates)
            if owner_username in tokens or owner_username in errors:
                continue

            # Look up the owner's account
            owner = user_repo.get_by_username(owner_username)
            if owner is None:
                errors[owner_username] = f"User '{owner_username}' not found"
                logger.warning(
                    f"Transaction token request: user '{owner_username}' not found"
                )
                continue

            if not owner.accounting_account_id:
                errors[owner_username] = (
                    f"User '{owner_username}' has no linked accounting account"
                )
                logger.warning(
                    f"Transaction token request: user '{owner_username}' has no account"
                )
                continue

            # Create pending transfer to this owner with their specific amount
            try:
                result = client.create_transfer(
                    source_account_id=current_user.accounting_account_id,
                    destination_account_id=owner.accounting_account_id,
                    amount=amount,
                    description=f"Payment to {owner_username}",
                    require_confirmation=True,
                )

                if result.success:
                    transfer: LedgerTransfer = result.data  # type: ignore[assignment]
                    if transfer.confirmation_token:
                        tokens[owner_username] = TokenInfo(
                            token=transfer.confirmation_token,
                            amount=amount,
                            transfer_id=transfer.id,
                        )
                        logger.debug(
                            f"Created confirmation token for owner '{owner_username}' "
                            f"with amount {amount}"
                        )
                    else:
                        errors[owner_username] = "No confirmation token returned"
                else:
                    errors[owner_username] = result.error or "Transfer creation failed"
                    logger.warning(
                        f"Failed to create transfer for '{owner_username}': {result.error}"
                    )

            except Exception as e:
                errors[owner_username] = f"Request failed: {e!s}"
                logger.error(f"Exception creating transfer for '{owner_username}': {e}")

        return TransactionTokensResponse(
            tokens=tokens,
            errors=errors,
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Error communicating with ledger service: {e!s}",
        ) from e
    finally:
        client.close()
