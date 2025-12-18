"""Tests for auth security module."""

from datetime import timedelta

import jwt
import pytest

from syfthub.auth.security import (
    ALGORITHM,
    blacklist_token,
    cleanup_expired_tokens,
    create_access_token,
    create_refresh_token,
    get_token_from_header,
    hash_password,
    is_token_blacklisted,
    token_blacklist,
    verify_password,
    verify_token,
)
from syfthub.core.config import settings


@pytest.fixture(autouse=True)
def clear_token_blacklist():
    """Clear token blacklist before and after each test."""
    token_blacklist.clear()
    yield
    token_blacklist.clear()


class TestPasswordHashing:
    """Test password hashing functions."""

    def test_hash_password(self):
        """Test password hashing."""
        password = "my_secure_password"
        hashed = hash_password(password)

        assert hashed != password
        assert len(hashed) > 0
        # Argon2 hashes start with $argon2
        assert hashed.startswith("$argon2")

    def test_verify_password_correct(self):
        """Test verifying correct password."""
        password = "my_secure_password"
        hashed = hash_password(password)

        assert verify_password(password, hashed) is True

    def test_verify_password_incorrect(self):
        """Test verifying incorrect password."""
        password = "my_secure_password"
        hashed = hash_password(password)

        assert verify_password("wrong_password", hashed) is False


class TestAccessToken:
    """Test access token creation and verification."""

    def test_create_access_token_basic(self):
        """Test creating access token with basic data."""
        data = {"sub": "123", "username": "testuser"}
        token = create_access_token(data)

        assert token is not None
        assert isinstance(token, str)
        assert len(token) > 0

    def test_create_access_token_with_int_sub(self):
        """Test creating access token with integer sub (should convert to string)."""
        data = {"sub": 123, "username": "testuser"}
        token = create_access_token(data)

        # Decode and verify sub was converted to string
        payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
        assert payload["sub"] == "123"
        assert isinstance(payload["sub"], str)

    def test_create_access_token_with_custom_expires(self):
        """Test creating access token with custom expiration."""
        data = {"sub": "123", "username": "testuser"}
        custom_delta = timedelta(hours=2)
        token = create_access_token(data, expires_delta=custom_delta)

        assert token is not None
        payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
        assert "exp" in payload
        assert payload["type"] == "access"

    def test_create_access_token_default_expiration(self):
        """Test access token has correct type claim."""
        data = {"sub": "123"}
        token = create_access_token(data)

        payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
        assert payload["type"] == "access"


class TestRefreshToken:
    """Test refresh token creation and verification."""

    def test_create_refresh_token_basic(self):
        """Test creating refresh token with basic data."""
        data = {"sub": "123", "username": "testuser"}
        token = create_refresh_token(data)

        assert token is not None
        assert isinstance(token, str)
        assert len(token) > 0

    def test_create_refresh_token_with_int_sub(self):
        """Test creating refresh token with integer sub (should convert to string)."""
        data = {"sub": 456, "username": "testuser"}
        token = create_refresh_token(data)

        # Decode and verify sub was converted to string
        payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
        assert payload["sub"] == "456"
        assert isinstance(payload["sub"], str)

    def test_create_refresh_token_with_custom_expires(self):
        """Test creating refresh token with custom expiration."""
        data = {"sub": "123", "username": "testuser"}
        custom_delta = timedelta(days=14)
        token = create_refresh_token(data, expires_delta=custom_delta)

        assert token is not None
        payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
        assert "exp" in payload
        assert payload["type"] == "refresh"

    def test_create_refresh_token_default_expiration(self):
        """Test refresh token has correct type claim."""
        data = {"sub": "123"}
        token = create_refresh_token(data)

        payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
        assert payload["type"] == "refresh"


class TestVerifyToken:
    """Test token verification."""

    def test_verify_token_success(self):
        """Test verifying valid access token."""
        data = {"sub": "123", "username": "testuser"}
        token = create_access_token(data)

        payload = verify_token(token, token_type="access")

        assert payload is not None
        assert payload["sub"] == "123"
        assert payload["username"] == "testuser"

    def test_verify_token_wrong_type(self):
        """Test verifying token with wrong type."""
        data = {"sub": "123", "username": "testuser"}
        access_token = create_access_token(data)

        # Try to verify access token as refresh token
        payload = verify_token(access_token, token_type="refresh")

        assert payload is None

    def test_verify_token_refresh_success(self):
        """Test verifying valid refresh token."""
        data = {"sub": "123", "username": "testuser"}
        token = create_refresh_token(data)

        payload = verify_token(token, token_type="refresh")

        assert payload is not None
        assert payload["sub"] == "123"

    def test_verify_token_invalid(self):
        """Test verifying invalid token."""
        payload = verify_token("invalid_token_string")

        assert payload is None

    def test_verify_token_expired(self):
        """Test verifying expired token."""
        data = {"sub": "123", "username": "testuser"}
        # Create token that's already expired
        expired_delta = timedelta(seconds=-10)
        token = create_access_token(data, expires_delta=expired_delta)

        payload = verify_token(token)

        assert payload is None

    def test_verify_token_blacklisted(self):
        """Test verifying blacklisted token."""
        data = {"sub": "123", "username": "testuser"}
        token = create_access_token(data)

        # Blacklist the token
        blacklist_token(token)

        payload = verify_token(token)

        assert payload is None


class TestTokenBlacklist:
    """Test token blacklist functionality."""

    def test_blacklist_token(self):
        """Test adding token to blacklist."""
        token = "test_token_123"
        blacklist_token(token)

        assert token in token_blacklist

    def test_is_token_blacklisted_true(self):
        """Test checking if token is blacklisted (true case)."""
        token = "blacklisted_token"
        token_blacklist.add(token)

        assert is_token_blacklisted(token) is True

    def test_is_token_blacklisted_false(self):
        """Test checking if token is blacklisted (false case)."""
        assert is_token_blacklisted("non_blacklisted_token") is False

    def test_cleanup_expired_tokens(self):
        """Test cleanup_expired_tokens function exists and runs without error."""
        # This is a placeholder function, just ensure it doesn't raise
        cleanup_expired_tokens()


class TestGetTokenFromHeader:
    """Test extracting token from Authorization header."""

    def test_get_token_from_header_valid(self):
        """Test extracting token from valid Bearer header."""
        header = "Bearer abc123token"
        token = get_token_from_header(header)

        assert token == "abc123token"

    def test_get_token_from_header_invalid_scheme(self):
        """Test extracting token from header with wrong scheme."""
        header = "Basic abc123token"
        token = get_token_from_header(header)

        assert token is None

    def test_get_token_from_header_empty(self):
        """Test extracting token from empty header."""
        token = get_token_from_header("")

        assert token is None

    def test_get_token_from_header_none(self):
        """Test extracting token from None header."""
        token = get_token_from_header(None)

        assert token is None

    def test_get_token_from_header_no_bearer_prefix(self):
        """Test extracting token from header without Bearer prefix."""
        header = "abc123token"
        token = get_token_from_header(header)

        assert token is None

    def test_get_token_from_header_bearer_only(self):
        """Test extracting token from header with Bearer but no token."""
        header = "Bearer "
        token = get_token_from_header(header)

        assert token == ""
