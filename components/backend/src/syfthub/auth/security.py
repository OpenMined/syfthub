"""Security utilities for authentication and authorization."""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

import jwt  # type: ignore[import-not-found]
from passlib.context import CryptContext  # type: ignore[import-untyped]

from syfthub.core.config import settings

# Password hashing context - using Argon2 for better security and no length limitations
pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")

# Token blacklist mapping token string to Unix expiration timestamp
token_blacklist: Dict[str, float] = {}

# Counter for periodic cleanup
_blacklist_insert_count: int = 0

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
    """Add a token to the blacklist with its expiration time.

    Extracts the ``exp`` claim from the JWT to determine when the token
    naturally expires. Expired entries are periodically purged to prevent
    unbounded memory growth.
    """
    global _blacklist_insert_count

    try:
        payload = jwt.decode(
            token, options={"verify_signature": False, "verify_exp": False}
        )
        exp = payload.get("exp")
    except Exception:
        exp = None

    if exp is None:
        # Conservative fallback: assume token lives for the configured access TTL
        exp = time.time() + settings.access_token_expire_minutes * 60

    token_blacklist[token] = float(exp)

    _blacklist_insert_count += 1
    if _blacklist_insert_count % 100 == 0:
        cleanup_expired_tokens()


def is_token_blacklisted(token: str) -> bool:
    """Check if a token is blacklisted.

    Performs lazy cleanup: if the entry has expired, removes it and
    returns ``False`` since the token would fail verification anyway.
    """
    if token not in token_blacklist:
        return False

    exp = token_blacklist[token]
    if exp < time.time():
        del token_blacklist[token]
        return False

    return True


def cleanup_expired_tokens() -> None:
    """Remove all expired entries from the token blacklist."""
    now = time.time()
    expired_tokens = [t for t, exp in token_blacklist.items() if exp < now]
    for t in expired_tokens:
        del token_blacklist[t]


def get_token_from_header(authorization: str) -> Optional[str]:
    """Extract token from Authorization header."""
    if not authorization or not authorization.startswith("Bearer "):
        return None
    return authorization.replace("Bearer ", "")
