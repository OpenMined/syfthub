"""Accounting proxy endpoints.

These endpoints proxy requests to the external accounting service,
avoiding CORS issues by making server-to-server calls.

The frontend calls these endpoints instead of the accounting service directly.
"""

from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from syfthub.auth.db_dependencies import get_current_active_user
from syfthub.schemas.user import User
from syfthub.services.accounting_client import AccountingClient

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
