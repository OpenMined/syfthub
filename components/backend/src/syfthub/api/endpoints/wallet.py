"""Wallet and MPP payment endpoints.

Provides wallet management (create, import, update) and Tempo blockchain
queries (balance, transactions).  The ``/pay`` endpoint is the Hub-side
client of the Machine Payments Protocol -- it creates a payment credential
on behalf of the authenticated user so the Hub can pay an endpoint owner's
MPP challenge.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from syfthub.auth.db_dependencies import get_current_active_user
from syfthub.core.config import settings
from syfthub.database.dependencies import get_user_repository
from syfthub.observability.logger import get_logger
from syfthub.repositories.user import UserRepository
from syfthub.schemas.user import (
    CreateWalletResponse,
    ImportWalletRequest,
    PaymentRequest,
    PaymentResponse,
    UpdateWalletAddressRequest,
    User,
    WalletBalanceResponse,
    WalletResponse,
    WalletTransaction,
)

logger = get_logger(__name__)

router = APIRouter()


# =============================================================================
# Wallet CRUD Endpoints
# =============================================================================


@router.get("/", response_model=WalletResponse)
async def get_wallet(
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> WalletResponse:
    """Get wallet info (address and existence) for the current user."""
    return WalletResponse(
        address=current_user.wallet_address,
        exists=current_user.wallet_address is not None,
    )


@router.post("/create", response_model=CreateWalletResponse)
async def create_wallet(
    current_user: Annotated[User, Depends(get_current_active_user)],
    user_repo: Annotated[UserRepository, Depends(get_user_repository)],
) -> CreateWalletResponse:
    """Generate a new Tempo keypair and store it on the user.

    Creates a fresh Ethereum account, derives a TempoAccount, and persists
    both the address and private key on the user record.  If a wallet already
    exists, the existing address is returned without creating a new one.
    """
    # Guard: if wallet already exists, return it instead of overwriting
    if current_user.wallet_address:
        return CreateWalletResponse(address=current_user.wallet_address)

    from eth_account import Account
    from mpp.methods.tempo import TempoAccount

    acct = Account.create()
    tempo_acct = TempoAccount.from_key(acct.key.hex())

    updated = user_repo.update(
        current_user.id,
        wallet_address=tempo_acct.address,
        wallet_private_key=tempo_acct.private_key,
    )
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to save wallet to user record",
        )

    logger.info(
        "wallet.created",
        user_id=current_user.id,
        wallet_address=tempo_acct.address,
    )

    return CreateWalletResponse(address=tempo_acct.address)


@router.post("/import", response_model=CreateWalletResponse)
async def import_wallet(
    request: ImportWalletRequest,
    current_user: Annotated[User, Depends(get_current_active_user)],
    user_repo: Annotated[UserRepository, Depends(get_user_repository)],
) -> CreateWalletResponse:
    """Import an existing wallet from a private key.

    Validates the private key by deriving a TempoAccount, then persists
    the address and private key on the user record.
    """
    from mpp.methods.tempo import TempoAccount

    try:
        tempo_acct = TempoAccount.from_key(request.private_key)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid private key: {e}",
        ) from e

    updated = user_repo.update(
        current_user.id,
        wallet_address=tempo_acct.address,
        wallet_private_key=tempo_acct.private_key,
    )
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to save wallet to user record",
        )

    logger.info(
        "wallet.imported",
        user_id=current_user.id,
        wallet_address=tempo_acct.address,
    )

    return CreateWalletResponse(address=tempo_acct.address)


@router.put("/", response_model=WalletResponse)
async def update_wallet_address(
    request: UpdateWalletAddressRequest,
    current_user: Annotated[User, Depends(get_current_active_user)],
    user_repo: Annotated[UserRepository, Depends(get_user_repository)],
) -> WalletResponse:
    """Update wallet address manually (without private key).

    Validates the address is a well-formed Ethereum address (0x + 40 hex chars).
    Note: updating only the address means the ``/pay`` endpoint will not work
    because it requires the private key.
    """
    # Clear private key since it belongs to the old address
    updated = user_repo.update(
        current_user.id,
        wallet_address=request.wallet_address,
        wallet_private_key=None,
    )
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update wallet address",
        )

    logger.info(
        "wallet.address_updated",
        user_id=current_user.id,
        wallet_address=request.wallet_address,
    )

    return WalletResponse(address=request.wallet_address, exists=True)


# =============================================================================
# Balance & Transaction Endpoints
# =============================================================================


@router.get("/balance", response_model=WalletBalanceResponse)
async def get_balance(
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> WalletBalanceResponse:
    """Query Tempo blockchain for the current user's pathUSD balance.

    Returns the balance and the 10 most recent transactions.  If the user
    has no wallet configured, returns a zero balance with
    ``wallet_configured=False``.
    """
    if not current_user.wallet_address:
        return WalletBalanceResponse(
            balance=0.0,
            currency="USD",
            recent_transactions=[],
            wallet_configured=False,
        )

    from syfthub.services.tempo_utils import (
        get_wallet_balance,
        get_wallet_transactions,
    )

    balance = await get_wallet_balance(current_user.wallet_address)
    recent_txs = await get_wallet_transactions(current_user.wallet_address)

    return WalletBalanceResponse(
        balance=balance,
        currency="USD",
        recent_transactions=[
            WalletTransaction(**tx) for tx in recent_txs[:10]
        ],
        wallet_configured=True,
    )


@router.get("/transactions", response_model=list[WalletTransaction])
async def get_transactions(
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> list[WalletTransaction]:
    """Get full transaction history from Tempo blockchain.

    Returns all recent transactions (up to ~1000 blocks back) for the
    current user's wallet.  Returns an empty list if no wallet is configured.
    """
    if not current_user.wallet_address:
        return []

    from syfthub.services.tempo_utils import get_wallet_transactions

    txs = await get_wallet_transactions(current_user.wallet_address)
    return [WalletTransaction(**tx) for tx in txs]


# =============================================================================
# MPP Payment Endpoint (Hub pays on behalf of user)
# =============================================================================


# TODO: Add per-user rate limiting to prevent runaway 402 payment loops
# (e.g., user with empty wallet repeatedly triggering aggregator → Hub → blockchain calls)
@router.post("/pay", response_model=PaymentResponse)
async def pay(
    request: PaymentRequest,
    current_user: Annotated[User, Depends(get_current_active_user)],
    user_repo: Annotated[UserRepository, Depends(get_user_repository)],
) -> PaymentResponse:
    """Create an MPP payment credential on behalf of the authenticated user.

    This is the **client-side** of the MPP flow.  When the Hub's aggregator
    receives a 402 Payment Required response from an endpoint, it calls this
    endpoint to create a payment credential using the user's stored wallet
    private key.

    The flow:
    1. Parse the 402 challenge from ``www_authenticate``
    2. Load the user's Tempo account from their stored private key
    3. Create a payment credential via ``client_method.create_credential()``
    4. Return the credential as an ``x_payment`` string
    """
    # Validate challenge size to prevent abuse
    if len(request.www_authenticate) > 10000:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "CHALLENGE_TOO_LARGE",
                "message": "Challenge too large",
            },
        )

    # Ensure user has a wallet address configured
    if not current_user.wallet_address:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "WALLET_NOT_CONFIGURED",
                "message": "No wallet configured. Please create or import a wallet first.",
            },
        )

    # Fetch the private key directly from the DB (not exposed on the User schema)
    wallet_private_key = user_repo.get_wallet_private_key(current_user.id)
    if not wallet_private_key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "WALLET_NOT_CONFIGURED",
                "message": "Wallet address exists but private key is missing. Please re-import your wallet.",
            },
        )

    try:
        from mpp import Challenge
        from mpp.methods.tempo import (
            TESTNET_CHAIN_ID,
            ChargeIntent,
            TempoAccount,
            tempo,
        )

        # 1. Parse the challenge from the www_authenticate header
        challenge = Challenge.from_www_authenticate(request.www_authenticate)

        # 2. Create TempoAccount from user's stored private key
        client_account = TempoAccount.from_key(wallet_private_key)

        # 3. Create a tempo method with the user's account (as the PAYER)
        chain_id = TESTNET_CHAIN_ID if settings.tempo_testnet else None
        client_method = tempo(
            account=client_account,
            chain_id=chain_id,
            intents={"charge": ChargeIntent(chain_id=chain_id)},
        )

        # 4. Create payment credential (this is async)
        credential = await client_method.create_credential(challenge)

        # 5. Serialize to x_payment string
        x_payment = credential.to_authorization()

        logger.info(
            "wallet.payment_created",
            user_id=current_user.id,
            endpoint_slug=request.endpoint_slug,
            wallet_address=current_user.wallet_address,
        )

        return PaymentResponse(x_payment=x_payment)

    except HTTPException:
        raise
    except Exception as e:
        error_msg = str(e).lower()
        logger.error(
            "wallet.payment_error",
            error=str(e),
            user_id=current_user.id,
            endpoint_slug=request.endpoint_slug,
            exc_info=True,
        )

        # Distinguish error types for actionable client responses
        if "insufficient funds" in error_msg or "insufficient balance" in error_msg:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "code": "INSUFFICIENT_BALANCE",
                    "message": f"Insufficient wallet balance: {e}",
                },
            ) from e
        elif "timeout" in error_msg or "timed out" in error_msg:
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail={
                    "code": "BLOCKCHAIN_TIMEOUT",
                    "message": f"Blockchain transaction timed out: {e}",
                },
            ) from e
        elif "invalid" in error_msg or "parse" in error_msg or "malformed" in error_msg:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={
                    "code": "INVALID_CHALLENGE",
                    "message": f"Invalid payment challenge: {e}",
                },
            ) from e
        else:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail={
                    "code": "PAYMENT_FAILED",
                    "message": f"Failed to create payment credential: {e}",
                },
            ) from e
