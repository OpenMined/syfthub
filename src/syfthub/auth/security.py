"""Security utilities for authentication and authorization."""

from __future__ import annotations

import base64
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt  # type: ignore[import-not-found]
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    PublicFormat,
)
from passlib.context import CryptContext  # type: ignore[import-untyped]

from syfthub.core.config import settings

# Password hashing context - using Argon2 for better security and no length limitations
pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")

# Token blacklist (in-memory for development, use Redis for production)
token_blacklist: set[str] = set()

# JWT algorithm
ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    """Hash a password using Argon2."""
    return pwd_context.hash(password)  # type: ignore[no-any-return]


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash."""
    return pwd_context.verify(plain_password, hashed_password)  # type: ignore[no-any-return]


def create_access_token(
    data: dict[str, Any], expires_delta: timedelta | None = None
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
    data: dict[str, Any], expires_delta: timedelta | None = None
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


def verify_token(token: str, token_type: str = "access") -> dict[str, Any] | None:
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


def get_token_from_header(authorization: str) -> str | None:
    """Extract token from Authorization header."""
    if not authorization or not authorization.startswith("Bearer "):
        return None
    return authorization.replace("Bearer ", "")


class Ed25519KeyPair:
    """Container for Ed25519 key pair."""

    def __init__(self, private_key: str, public_key: str) -> None:
        """Initialize key pair with base64 encoded keys."""
        self.private_key = private_key
        self.public_key = public_key


def generate_ed25519_key_pair() -> Ed25519KeyPair:
    """Generate a new Ed25519 key pair.

    Returns:
        Ed25519KeyPair with base64 encoded private and public keys.
    """
    # Generate private key
    private_key = Ed25519PrivateKey.generate()

    # Get public key from private key
    public_key = private_key.public_key()

    # Serialize private key to bytes
    private_key_bytes = private_key.private_bytes(
        encoding=Encoding.Raw,
        format=PrivateFormat.Raw,
        encryption_algorithm=NoEncryption(),
    )

    # Serialize public key to bytes
    public_key_bytes = public_key.public_bytes(
        encoding=Encoding.Raw, format=PublicFormat.Raw
    )

    # Encode to base64 for storage/transmission
    private_key_b64 = base64.b64encode(private_key_bytes).decode("utf-8")
    public_key_b64 = base64.b64encode(public_key_bytes).decode("utf-8")

    return Ed25519KeyPair(private_key_b64, public_key_b64)


def verify_ed25519_signature(message: bytes, signature: str, public_key: str) -> bool:
    """Verify an Ed25519 signature.

    Args:
        message: The original message that was signed (as bytes)
        signature: Base64 encoded signature
        public_key: Base64 encoded public key

    Returns:
        True if signature is valid, False otherwise.
    """
    try:
        # Decode base64 inputs
        signature_bytes = base64.b64decode(signature)
        public_key_bytes = base64.b64decode(public_key)

        # Reconstruct public key object
        public_key_obj = Ed25519PublicKey.from_public_bytes(public_key_bytes)

        # Verify signature
        public_key_obj.verify(signature_bytes, message)
        return True
    except Exception:
        # Any exception means verification failed
        return False


def sign_message_ed25519(message: bytes, private_key: str) -> str:
    """Sign a message with Ed25519 private key.

    Args:
        message: The message to sign (as bytes)
        private_key: Base64 encoded private key

    Returns:
        Base64 encoded signature.
    """
    # Decode private key
    private_key_bytes = base64.b64decode(private_key)

    # Reconstruct private key object
    private_key_obj = Ed25519PrivateKey.from_private_bytes(private_key_bytes)

    # Sign message
    signature_bytes = private_key_obj.sign(message)

    # Return base64 encoded signature
    return base64.b64encode(signature_bytes).decode("utf-8")
