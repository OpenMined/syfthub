"""API Token utilities for generation, hashing, and verification.

This module provides secure utilities for managing API tokens:
- Token generation with cryptographically secure random bytes
- SHA-256 hashing for secure storage
- Format validation and prefix extraction

Security considerations:
- Tokens are generated with 256 bits of entropy (32 bytes)
- Tokens are stored as SHA-256 hashes, never in plaintext
- Timing-safe comparison is used to prevent timing attacks
"""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets
from typing import Tuple

# Token format constants
TOKEN_PREFIX = "syft_pat_"  # syft personal access token
TOKEN_RANDOM_BYTES = 32  # 256 bits of entropy
TOKEN_PREFIX_LENGTH = 16  # Display prefix length (e.g., "syft_pat_aB3dE5fG")

# Token format regex: syft_pat_ followed by base64url characters
TOKEN_PATTERN = re.compile(r"^syft_pat_[A-Za-z0-9_-]{43}$")

# Generic syft token pattern (for detection)
SYFT_TOKEN_PATTERN = re.compile(r"^syft_[a-z]+_[A-Za-z0-9_-]+$")


def generate_api_token() -> Tuple[str, str, str]:
    """Generate a new API token with its hash and prefix.

    Returns a tuple of:
    - full_token: The complete token to give to the user (shown once!)
    - token_hash: SHA-256 hex digest for database storage
    - token_prefix: First 16 chars for display/identification

    Example:
        >>> token, hash, prefix = generate_api_token()
        >>> print(token)  # syft_pat_aB3dE5fG7hI9jK1lM3nO5pQ7rS9tU1vW3xY5z
        >>> print(prefix)  # syft_pat_aB3dE5fG

    Returns:
        Tuple of (full_token, token_hash, token_prefix)
    """
    # Generate cryptographically secure random bytes
    random_part = secrets.token_urlsafe(TOKEN_RANDOM_BYTES)

    # Construct the full token
    full_token = f"{TOKEN_PREFIX}{random_part}"

    # Generate hash for storage
    token_hash = hash_api_token(full_token)

    # Extract prefix for display
    token_prefix = get_token_prefix(full_token)

    return full_token, token_hash, token_prefix


def hash_api_token(token: str) -> str:
    """Create a SHA-256 hash of an API token.

    SHA-256 is appropriate for API tokens because:
    1. Tokens have high entropy (256 bits), making brute-force infeasible
    2. Fast verification is important for authentication performance
    3. No salt is needed because tokens aren't user-chosen (no rainbow tables)

    Args:
        token: The full API token string.

    Returns:
        Hex digest of the SHA-256 hash (64 characters).
    """
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def get_token_prefix(token: str) -> str:
    """Extract the display prefix from an API token.

    The prefix includes the token type identifier and first few random
    characters, allowing users to identify their tokens without exposing
    the full value.

    Args:
        token: The full API token string.

    Returns:
        First 16 characters of the token (e.g., "syft_pat_aB3dE5fG").
    """
    return token[:TOKEN_PREFIX_LENGTH]


def is_api_token(token: str) -> bool:
    """Check if a string looks like a SyftHub API token.

    This is used during authentication to quickly determine whether to
    use API token auth or JWT auth, based on the token prefix.

    Args:
        token: The token string to check.

    Returns:
        True if the token starts with "syft_", False otherwise.
    """
    return token.startswith("syft_")


def verify_api_token_format(token: str) -> bool:
    """Validate that a token has the correct format.

    Checks that the token:
    1. Starts with "syft_pat_"
    2. Has the correct length
    3. Contains only valid base64url characters

    Args:
        token: The token string to validate.

    Returns:
        True if the token format is valid, False otherwise.
    """
    return bool(TOKEN_PATTERN.match(token))


def secure_compare(a: str, b: str) -> bool:
    """Perform a timing-safe string comparison.

    Uses hmac.compare_digest to prevent timing attacks when comparing
    tokens or hashes.

    Args:
        a: First string to compare.
        b: Second string to compare.

    Returns:
        True if strings are equal, False otherwise.
    """
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


def mask_token(token: str) -> str:
    """Mask an API token for safe logging/display.

    Shows the prefix and masks the rest with asterisks.

    Args:
        token: The full API token string.

    Returns:
        Masked token string (e.g., "syft_pat_aB3d****").

    Example:
        >>> mask_token("syft_pat_aB3dE5fG7hI9jK1lM3nO5pQ7rS9tU1vW3xY5z")
        'syft_pat_aB3d****'
    """
    if len(token) <= TOKEN_PREFIX_LENGTH:
        return token
    prefix = token[: TOKEN_PREFIX_LENGTH - 4]  # Leave room for ****
    return f"{prefix}****"
