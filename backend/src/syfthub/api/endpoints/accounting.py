"""Accounting proxy endpoints.

These endpoints proxy requests to the external accounting service,
avoiding CORS issues by making server-to-server calls.

The frontend calls these endpoints instead of the accounting service directly.
"""

import logging
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from syfthub.auth.db_dependencies import get_current_active_user
from syfthub.database.dependencies import get_user_repository
from syfthub.repositories.user import UserRepository
from syfthub.schemas.user import User
from syfthub.services.accounting_client import AccountingClient

logger = logging.getLogger(__name__)

router = APIRouter()


# =============================================================================
# Response Models
# =============================================================================


class AccountingUserResponse(BaseModel):
    """Accounting user info response."""

    id: str
    email: str
    balance: float
    organization: Optional[str] = None


class AccountingTransactionResponse(BaseModel):
    """Accounting transaction response."""

    id: str
    senderEmail: str = Field(alias="sender_email")
    recipientEmail: str = Field(alias="recipient_email")
    amount: float
    status: str
    createdBy: str = Field(alias="created_by")
    resolvedBy: Optional[str] = Field(None, alias="resolved_by")
    createdAt: str = Field(alias="created_at")
    resolvedAt: Optional[str] = Field(None, alias="resolved_at")
    appName: Optional[str] = Field(None, alias="app_name")
    appEpPath: Optional[str] = Field(None, alias="app_ep_path")

    class Config:
        populate_by_name = True


class CreateTransactionRequest(BaseModel):
    """Create transaction request."""

    recipientEmail: str = Field(alias="recipient_email")
    amount: float
    appName: Optional[str] = Field(None, alias="app_name")
    appEpPath: Optional[str] = Field(None, alias="app_ep_path")

    class Config:
        populate_by_name = True


class CreateTransactionTokensRequest(BaseModel):
    """Request to create transaction tokens for multiple endpoint owners.

    Used by the chat flow to pre-authorize payments to endpoint owners.
    """

    owner_usernames: list[str] = Field(
        ...,
        description="List of endpoint owner usernames to create tokens for",
        min_length=1,
        max_length=20,
    )


class TransactionTokensResponse(BaseModel):
    """Response containing transaction tokens for endpoint owners.

    Maps owner_username to their transaction token.
    Missing entries indicate the token could not be created for that owner.
    """

    tokens: dict[str, str] = Field(
        default_factory=dict,
        description="Mapping of owner_username to transaction token",
    )
    errors: dict[str, str] = Field(
        default_factory=dict,
        description="Mapping of owner_username to error message (if token creation failed)",
    )


# =============================================================================
# Helper Functions
# =============================================================================


def get_accounting_client(user: User) -> tuple[AccountingClient, str]:
    """Get an accounting client configured with user's credentials.

    Args:
        user: The current user with accounting credentials

    Returns:
        Tuple of (AccountingClient, validated_password)

    Raises:
        HTTPException: If accounting is not configured for the user
    """
    if not user.accounting_service_url or not user.accounting_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Accounting not configured. Please set up billing in settings.",
        )
    return AccountingClient(user.accounting_service_url), user.accounting_password


# =============================================================================
# Endpoints
# =============================================================================


@router.get("/user", response_model=AccountingUserResponse)
async def get_accounting_user(
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> AccountingUserResponse:
    """Get current user's accounting info including balance.

    Proxies the request to the external accounting service using
    the user's stored credentials.
    """
    client, password = get_accounting_client(current_user)

    try:
        user_info = client.get_user(
            current_user.email,
            password,
        )

        if not user_info:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid accounting credentials",
            )

        return AccountingUserResponse(
            id=user_info.id,
            email=user_info.email,
            balance=user_info.balance,
            organization=user_info.organization,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Error communicating with accounting service: {e!s}",
        ) from e
    finally:
        client.close()


@router.get("/transactions", response_model=list[AccountingTransactionResponse])
async def get_transactions(
    current_user: Annotated[User, Depends(get_current_active_user)],
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
) -> list[AccountingTransactionResponse]:
    """Get user's transaction history.

    Proxies the request to the external accounting service.
    """
    client, password = get_accounting_client(current_user)

    try:
        response = client.client.get(
            "/transactions",
            params={"skip": skip, "limit": limit},
            auth=(current_user.email, password),
        )

        if response.status_code != 200:
            raise HTTPException(
                status_code=response.status_code,
                detail="Failed to fetch transactions",
            )

        transactions_data = response.json()

        # Transform the response to match frontend expectations
        result = []
        for tx in transactions_data:
            result.append(
                AccountingTransactionResponse(
                    id=tx.get("id", ""),
                    sender_email=tx.get("senderEmail", ""),
                    recipient_email=tx.get("recipientEmail", ""),
                    amount=tx.get("amount", 0),
                    status=tx.get("status", ""),
                    created_by=tx.get("createdBy", ""),
                    resolved_by=tx.get("resolvedBy"),
                    created_at=tx.get("createdAt", ""),
                    resolved_at=tx.get("resolvedAt"),
                    app_name=tx.get("appName"),
                    app_ep_path=tx.get("appEpPath"),
                )
            )

        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Error communicating with accounting service: {e!s}",
        ) from e
    finally:
        client.close()


@router.post("/transactions", response_model=AccountingTransactionResponse)
async def create_transaction(
    request: CreateTransactionRequest,
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> AccountingTransactionResponse:
    """Create a new transaction.

    Proxies the request to the external accounting service.
    """
    client, password = get_accounting_client(current_user)

    try:
        payload = {
            "recipientEmail": request.recipientEmail,
            "amount": request.amount,
        }
        if request.appName:
            payload["appName"] = request.appName
        if request.appEpPath:
            payload["appEpPath"] = request.appEpPath

        response = client.client.post(
            "/transactions",
            json=payload,
            auth=(current_user.email, password),
        )

        if response.status_code not in (200, 201):
            detail = "Failed to create transaction"
            try:
                error_data = response.json()
                detail = error_data.get("detail", error_data.get("message", detail))
            except Exception:
                pass
            raise HTTPException(status_code=response.status_code, detail=detail)

        tx = response.json()
        return AccountingTransactionResponse(
            id=tx.get("id", ""),
            sender_email=tx.get("senderEmail", ""),
            recipient_email=tx.get("recipientEmail", ""),
            amount=tx.get("amount", 0),
            status=tx.get("status", ""),
            created_by=tx.get("createdBy", ""),
            resolved_by=tx.get("resolvedBy"),
            created_at=tx.get("createdAt", ""),
            resolved_at=tx.get("resolvedAt"),
            app_name=tx.get("appName"),
            app_ep_path=tx.get("appEpPath"),
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Error communicating with accounting service: {e!s}",
        ) from e
    finally:
        client.close()


@router.post("/transactions/{transaction_id}/confirm")
async def confirm_transaction(
    transaction_id: str,
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> AccountingTransactionResponse:
    """Confirm a pending transaction.

    Proxies the request to the external accounting service.
    """
    client, password = get_accounting_client(current_user)

    try:
        response = client.client.post(
            f"/transactions/{transaction_id}/confirm",
            auth=(current_user.email, password),
        )

        if response.status_code != 200:
            detail = "Failed to confirm transaction"
            try:
                error_data = response.json()
                detail = error_data.get("detail", error_data.get("message", detail))
            except Exception:
                pass
            raise HTTPException(status_code=response.status_code, detail=detail)

        tx = response.json()
        return AccountingTransactionResponse(
            id=tx.get("id", ""),
            sender_email=tx.get("senderEmail", ""),
            recipient_email=tx.get("recipientEmail", ""),
            amount=tx.get("amount", 0),
            status=tx.get("status", ""),
            created_by=tx.get("createdBy", ""),
            resolved_by=tx.get("resolvedBy"),
            created_at=tx.get("createdAt", ""),
            resolved_at=tx.get("resolvedAt"),
            app_name=tx.get("appName"),
            app_ep_path=tx.get("appEpPath"),
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Error communicating with accounting service: {e!s}",
        ) from e
    finally:
        client.close()


@router.post("/transactions/{transaction_id}/cancel")
async def cancel_transaction(
    transaction_id: str,
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> AccountingTransactionResponse:
    """Cancel a pending transaction.

    Proxies the request to the external accounting service.
    """
    client, password = get_accounting_client(current_user)

    try:
        response = client.client.post(
            f"/transactions/{transaction_id}/cancel",
            auth=(current_user.email, password),
        )

        if response.status_code != 200:
            detail = "Failed to cancel transaction"
            try:
                error_data = response.json()
                detail = error_data.get("detail", error_data.get("message", detail))
            except Exception:
                pass
            raise HTTPException(status_code=response.status_code, detail=detail)

        tx = response.json()
        return AccountingTransactionResponse(
            id=tx.get("id", ""),
            sender_email=tx.get("senderEmail", ""),
            recipient_email=tx.get("recipientEmail", ""),
            amount=tx.get("amount", 0),
            status=tx.get("status", ""),
            created_by=tx.get("createdBy", ""),
            resolved_by=tx.get("resolvedBy"),
            created_at=tx.get("createdAt", ""),
            resolved_at=tx.get("resolvedAt"),
            app_name=tx.get("appName"),
            app_ep_path=tx.get("appEpPath"),
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Error communicating with accounting service: {e!s}",
        ) from e
    finally:
        client.close()


@router.post("/transaction-tokens", response_model=TransactionTokensResponse)
async def create_transaction_tokens(
    request: CreateTransactionTokensRequest,
    current_user: Annotated[User, Depends(get_current_active_user)],
    user_repo: Annotated[UserRepository, Depends(get_user_repository)],
) -> TransactionTokensResponse:
    """Create transaction tokens for multiple endpoint owners.

    This endpoint is used by the chat flow to pre-authorize payments to
    endpoint owners before making requests to their endpoints.

    For each owner username:
    1. Looks up the owner's email from the database
    2. Creates a transaction token via the accounting service
    3. Returns the token (or error) for each owner

    Transaction tokens are short-lived JWTs that authorize the recipient
    (endpoint owner) to create a delegated transaction charging the sender
    (current user).

    Args:
        request: List of owner usernames to create tokens for
        current_user: The authenticated user (will be charged)
        user_repo: Repository for looking up user emails

    Returns:
        TransactionTokensResponse with tokens and any errors
    """
    # Check if current user has accounting configured
    if not current_user.accounting_service_url or not current_user.accounting_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Accounting not configured. Please set up billing in settings.",
        )

    client = AccountingClient(current_user.accounting_service_url)
    password = current_user.accounting_password

    tokens: dict[str, str] = {}
    errors: dict[str, str] = {}

    try:
        for owner_username in request.owner_usernames:
            # Skip if we've already processed this username (handle duplicates)
            if owner_username in tokens or owner_username in errors:
                continue

            # Look up the owner's email
            owner = user_repo.get_by_username(owner_username)
            if owner is None:
                errors[owner_username] = f"User '{owner_username}' not found"
                logger.warning(
                    f"Transaction token request: user '{owner_username}' not found"
                )
                continue

            if not owner.email:
                errors[owner_username] = f"User '{owner_username}' has no email"
                logger.warning(
                    f"Transaction token request: user '{owner_username}' has no email"
                )
                continue

            # Create transaction token for this owner
            try:
                response = client.client.post(
                    "/tokens",
                    json={"recipientEmail": owner.email},
                    auth=(current_user.email, password),
                )

                if response.status_code in (200, 201):
                    token_data = response.json()
                    token = token_data.get("token")
                    if token:
                        tokens[owner_username] = token
                        logger.debug(
                            f"Created transaction token for owner '{owner_username}'"
                        )
                    else:
                        errors[owner_username] = (
                            "Token not returned by accounting service"
                        )
                else:
                    # Extract error detail
                    try:
                        error_data = response.json()
                        detail = error_data.get(
                            "detail",
                            error_data.get("message", f"HTTP {response.status_code}"),
                        )
                    except Exception:
                        detail = f"HTTP {response.status_code}"
                    errors[owner_username] = detail
                    logger.warning(
                        f"Failed to create transaction token for '{owner_username}': {detail}"
                    )

            except Exception as e:
                errors[owner_username] = f"Request failed: {e!s}"
                logger.error(
                    f"Exception creating transaction token for '{owner_username}': {e}"
                )

        return TransactionTokensResponse(tokens=tokens, errors=errors)

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Error communicating with accounting service: {e!s}",
        ) from e
    finally:
        client.close()
