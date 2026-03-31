"""Security utilities for authentication and authorization."""

from __future__ import annotations

import base64
import hashlib
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Set

import jwt  # type: ignore[import-not-found]
from cryptography.fernet import Fernet
from passlib.context import CryptContext  # type: ignore[import-untyped]

from syfthub.core.config import settings

logger = logging.getLogger(__name__)

# Password hashing context - using Argon2 for better security and no length limitations
pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")

# Token blacklist (in-memory for development, use Redis for production)
token_blacklist: Set[str] = set()

# JWT algorithm
ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    """Hash a password using Argon2."""
    return pwd_context.hash(password)  # type: ignore[no-any-return]


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash."""
    return pwd_context.verify(plain_password, hashed_password)  # type: ignore[no-any-return]


def create_access_token(
    data: Dict[str, Any], expires_delta: Optional[timedelta] = None
) -> str:
    """Create a JWT access token."""
    to_encode = data.copy()

    # Ensure 'sub' is a string (JWT requirement)
    if "sub" in to_encode and not isinstance(to_encode["sub"], str):
        to_encode["sub"] = str(to_encode["sub"])

    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(
            minutes=settings.access_token_expire_minutes
        )

    to_encode.update({"exp": expire, "type": "access"})
    return jwt.encode(to_encode, settings.secret_key, algorithm=ALGORITHM)  # type: ignore[no-any-return]


def create_refresh_token(
    data: Dict[str, Any], expires_delta: Optional[timedelta] = None
) -> str:
    """Create a JWT refresh token."""
    to_encode = data.copy()

    # Ensure 'sub' is a string (JWT requirement)
    if "sub" in to_encode and not isinstance(to_encode["sub"], str):
        to_encode["sub"] = str(to_encode["sub"])

    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(
            days=settings.refresh_token_expire_days
        )

    to_encode.update({"exp": expire, "type": "refresh"})
    return jwt.encode(to_encode, settings.secret_key, algorithm=ALGORITHM)  # type: ignore[no-any-return]


def verify_token(token: str, token_type: str = "access") -> Optional[Dict[str, Any]]:
    """Verify a JWT token and return its payload."""
    try:
        # Check if token is blacklisted
        if is_token_blacklisted(token):
            return None

        payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])

        # Verify token type
        if payload.get("type") != token_type:
            return None

        return payload  # type: ignore[no-any-return]
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


def blacklist_token(token: str) -> None:
    """Add a token to the blacklist."""
    token_blacklist.add(token)


def is_token_blacklisted(token: str) -> bool:
    """Check if a token is blacklisted."""
    return token in token_blacklist


def cleanup_expired_tokens() -> None:
    """Clean up expired tokens from blacklist (for production use with scheduled job)."""
    # In a real application, you would implement this with Redis or database
    # For now, this is a placeholder for the cleanup logic
    pass


def get_token_from_header(authorization: str) -> Optional[str]:
    """Extract token from Authorization header."""
    if not authorization or not authorization.startswith("Bearer "):
        return None
    return authorization.replace("Bearer ", "")


# =============================================================================
# Fernet Encryption for Sensitive Fields (e.g. accounting_password)
# =============================================================================

_fernet_instance: Optional[Fernet] = None


def _get_fernet() -> Fernet:
    """Return a cached Fernet instance, creating it on first call.

    Uses ``settings.accounting_encryption_key`` if set, otherwise derives a
    Fernet-compatible key from ``settings.secret_key`` via SHA-256.  The
    derived-key path is a convenience for development; production deployments
    should always set an explicit encryption key.
    """
    global _fernet_instance
    if _fernet_instance is not None:
        return _fernet_instance

    key = settings.accounting_encryption_key
    if key:
        _fernet_instance = Fernet(key.encode() if isinstance(key, str) else key)
    else:
        # Derive a Fernet key from secret_key (development fallback)
        logger.warning(
            "ACCOUNTING_ENCRYPTION_KEY not set — deriving encryption key from "
            "SECRET_KEY. Set an explicit key for production."
        )
        digest = hashlib.sha256(settings.secret_key.encode()).digest()
        fernet_key = base64.urlsafe_b64encode(digest)
        _fernet_instance = Fernet(fernet_key)

    return _fernet_instance


def encrypt_field(plaintext: str) -> str:
    """Encrypt a plaintext string and return the Fernet token as a string.

    The returned value is safe to store in a VARCHAR/Text column.
    """
    f = _get_fernet()
    return f.encrypt(plaintext.encode()).decode()


def decrypt_field(ciphertext: str) -> str:
    """Decrypt a Fernet-encrypted string and return the original plaintext.

    Raises ``cryptography.fernet.InvalidToken`` if the ciphertext is
    corrupted or was encrypted with a different key.
    """
    f = _get_fernet()
    return f.decrypt(ciphertext.encode()).decode()
