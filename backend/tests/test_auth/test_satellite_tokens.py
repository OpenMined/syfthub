"""Unit tests for Satellite Token Service.

Tests the audience-bound token creation and verification functionality
for the Identity Provider.
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import jwt
import pytest

from syfthub.auth.keys import RSAKeyManager
from syfthub.auth.satellite_tokens import (
    TokenVerificationResult,
    create_satellite_token,
    decode_satellite_token,
    get_allowed_audiences,
    validate_audience,
    verify_satellite_token_for_service,
)
from syfthub.domain.exceptions import InvalidAudienceError, KeyNotConfiguredError


class TestAudienceValidation:
    """Tests for audience validation functions."""

    def test_validate_audience_valid(self):
        """Test that valid audience passes validation."""
        with patch("syfthub.auth.satellite_tokens.settings") as mock_settings:
            mock_settings.allowed_audiences = {"syftai-space", "syft-billing"}

            assert validate_audience("syftai-space") is True
            assert validate_audience("SYFTAI-SPACE") is True  # Case insensitive
            assert validate_audience("  syftai-space  ") is True  # Whitespace

    def test_validate_audience_invalid(self):
        """Test that invalid audience fails validation."""
        with patch("syfthub.auth.satellite_tokens.settings") as mock_settings:
            mock_settings.allowed_audiences = {"syftai-space"}

            assert validate_audience("unknown-service") is False
            assert validate_audience("syft-mars") is False

    def test_get_allowed_audiences(self):
        """Test retrieving allowed audiences."""
        with patch("syfthub.auth.satellite_tokens.settings") as mock_settings:
            mock_settings.allowed_audiences = {"syftai-space", "syft-billing"}

            audiences = get_allowed_audiences()

            assert "syftai-space" in audiences
            assert "syft-billing" in audiences


class TestSatelliteTokenCreation:
    """Tests for satellite token creation."""

    @pytest.fixture
    def mock_user(self):
        """Create a mock user for testing."""
        user = MagicMock()
        user.id = 123
        user.role = "user"
        user.username = "testuser"
        return user

    @pytest.fixture
    def configured_key_manager(self):
        """Create a configured key manager for testing."""
        # Reset singleton
        RSAKeyManager._instance = None
        manager = RSAKeyManager()
        manager._generate_keypair("test-key-123")
        yield manager
        RSAKeyManager._instance = None

    @pytest.fixture
    def unconfigured_key_manager(self):
        """Create an unconfigured key manager for testing."""
        RSAKeyManager._instance = None
        manager = RSAKeyManager()
        yield manager
        RSAKeyManager._instance = None

    def test_create_satellite_token_valid(self, mock_user, configured_key_manager):
        """Test creating a valid satellite token."""
        with patch("syfthub.auth.satellite_tokens.settings") as mock_settings:
            mock_settings.allowed_audiences = {"syftai-space"}
            mock_settings.issuer_url = "https://hub.syft.com"
            mock_settings.satellite_token_expire_seconds = 60

            token = create_satellite_token(
                user=mock_user,
                audience="syftai-space",
                key_manager=configured_key_manager,
            )

            assert isinstance(token, str)
            assert len(token) > 0

            # Token should be a valid JWT format (three parts)
            parts = token.split(".")
            assert len(parts) == 3

    def test_satellite_token_claims(self, mock_user, configured_key_manager):
        """Test that satellite token contains required claims."""
        with patch("syfthub.auth.satellite_tokens.settings") as mock_settings:
            mock_settings.allowed_audiences = {"syftai-space"}
            mock_settings.issuer_url = "https://hub.syft.com"
            mock_settings.satellite_token_expire_seconds = 60

            token = create_satellite_token(
                user=mock_user,
                audience="syftai-space",
                key_manager=configured_key_manager,
            )

            # Decode without verification to check claims
            payload = jwt.decode(token, options={"verify_signature": False})

            # Check required claims (FR-07)
            assert payload["sub"] == "123"  # User ID as string
            assert payload["iss"] == "https://hub.syft.com"
            assert payload["aud"] == "syftai-space"
            assert payload["role"] == "user"
            assert "exp" in payload
            assert "iat" in payload

    def test_satellite_token_kid_header(self, mock_user, configured_key_manager):
        """Test that satellite token includes kid in header (FR-08)."""
        with patch("syfthub.auth.satellite_tokens.settings") as mock_settings:
            mock_settings.allowed_audiences = {"syftai-space"}
            mock_settings.issuer_url = "https://hub.syft.com"
            mock_settings.satellite_token_expire_seconds = 60

            token = create_satellite_token(
                user=mock_user,
                audience="syftai-space",
                key_manager=configured_key_manager,
            )

            # Get unverified header
            header = jwt.get_unverified_header(token)

            assert header["alg"] == "RS256"
            assert header["kid"] == "test-key-123"

    def test_satellite_token_expiry(self, mock_user, configured_key_manager):
        """Test that satellite token has correct expiry."""
        with patch("syfthub.auth.satellite_tokens.settings") as mock_settings:
            mock_settings.allowed_audiences = {"syftai-space"}
            mock_settings.issuer_url = "https://hub.syft.com"
            mock_settings.satellite_token_expire_seconds = 60

            before = datetime.now(timezone.utc).timestamp()

            token = create_satellite_token(
                user=mock_user,
                audience="syftai-space",
                key_manager=configured_key_manager,
            )

            after = datetime.now(timezone.utc).timestamp()

            payload = jwt.decode(token, options={"verify_signature": False})

            # Expiry should be ~60 seconds from now
            exp = payload["exp"]
            iat = payload["iat"]

            # Token should expire within the expected window (with 2s tolerance)
            assert exp - iat == 60
            assert exp >= before + 58  # Allow 2s tolerance
            assert exp <= after + 62  # Allow 2s tolerance

    def test_invalid_audience_rejected(self, mock_user, configured_key_manager):
        """Test that invalid audience raises error (FR-06)."""
        with patch("syfthub.auth.satellite_tokens.settings") as mock_settings:
            mock_settings.allowed_audiences = {"syftai-space"}

            with pytest.raises(InvalidAudienceError) as exc_info:
                create_satellite_token(
                    user=mock_user,
                    audience="unknown-service",
                    key_manager=configured_key_manager,
                )

            assert "unknown-service" in str(exc_info.value.message)

    def test_key_not_configured_error(self, mock_user, unconfigured_key_manager):
        """Test that unconfigured keys raise error."""
        with patch("syfthub.auth.satellite_tokens.settings") as mock_settings:
            mock_settings.allowed_audiences = {"syftai-space"}

            with pytest.raises(KeyNotConfiguredError):
                create_satellite_token(
                    user=mock_user,
                    audience="syftai-space",
                    key_manager=unconfigured_key_manager,
                )

    def test_token_verifiable_with_public_key(self, mock_user, configured_key_manager):
        """Test that token can be verified with the public key."""
        with patch("syfthub.auth.satellite_tokens.settings") as mock_settings:
            mock_settings.allowed_audiences = {"syftai-space"}
            mock_settings.issuer_url = "https://hub.syft.com"
            mock_settings.satellite_token_expire_seconds = 60

            token = create_satellite_token(
                user=mock_user,
                audience="syftai-space",
                key_manager=configured_key_manager,
            )

            # Verify token using the public key
            public_key = configured_key_manager.get_public_key("test-key-123")
            payload = jwt.decode(
                token,
                public_key,
                algorithms=["RS256"],
                audience="syftai-space",
                issuer="https://hub.syft.com",
            )

            assert payload["sub"] == "123"
            assert payload["aud"] == "syftai-space"

    def test_token_verification_fails_with_wrong_audience(
        self, mock_user, configured_key_manager
    ):
        """Test that token verification fails with wrong audience."""
        with patch("syfthub.auth.satellite_tokens.settings") as mock_settings:
            mock_settings.allowed_audiences = {"syftai-space"}
            mock_settings.issuer_url = "https://hub.syft.com"
            mock_settings.satellite_token_expire_seconds = 60

            token = create_satellite_token(
                user=mock_user,
                audience="syftai-space",
                key_manager=configured_key_manager,
            )

            # Try to verify with wrong audience
            public_key = configured_key_manager.get_public_key("test-key-123")

            with pytest.raises(jwt.InvalidAudienceError):
                jwt.decode(
                    token,
                    public_key,
                    algorithms=["RS256"],
                    audience="syft-billing",  # Wrong audience
                    issuer="https://hub.syft.com",
                )


class TestSatelliteTokenDecoding:
    """Tests for satellite token decoding (helper function)."""

    @pytest.fixture
    def mock_user(self):
        """Create a mock user for testing."""
        user = MagicMock()
        user.id = 456
        user.role = "admin"
        return user

    @pytest.fixture
    def configured_key_manager(self):
        """Create a configured key manager for testing."""
        RSAKeyManager._instance = None
        manager = RSAKeyManager()
        manager._generate_keypair("decode-test-key")
        yield manager
        RSAKeyManager._instance = None

    def test_decode_satellite_token_success(self, mock_user, configured_key_manager):
        """Test successful token decoding."""
        with patch("syfthub.auth.satellite_tokens.settings") as mock_settings:
            mock_settings.allowed_audiences = {"syftai-space"}
            mock_settings.issuer_url = "https://hub.syft.com"
            mock_settings.satellite_token_expire_seconds = 60

            token = create_satellite_token(
                user=mock_user,
                audience="syftai-space",
                key_manager=configured_key_manager,
            )

            payload = decode_satellite_token(
                token=token,
                key_manager=configured_key_manager,
                audience="syftai-space",
            )

            assert payload["sub"] == "456"
            assert payload["role"] == "admin"
            assert payload["aud"] == "syftai-space"

    def test_decode_satellite_token_invalid_kid(self, configured_key_manager):
        """Test decoding token with unknown key ID."""
        # Create a token with a different key manager (different kid)
        RSAKeyManager._instance = None
        other_manager = RSAKeyManager()
        other_manager._generate_keypair("other-key")

        mock_user = MagicMock()
        mock_user.id = 789
        mock_user.role = "user"

        with patch("syfthub.auth.satellite_tokens.settings") as mock_settings:
            mock_settings.allowed_audiences = {"syftai-space"}
            mock_settings.issuer_url = "https://hub.syft.com"
            mock_settings.satellite_token_expire_seconds = 60

            token = create_satellite_token(
                user=mock_user,
                audience="syftai-space",
                key_manager=other_manager,
            )

            # Try to decode with different key manager
            with pytest.raises(jwt.InvalidTokenError):
                decode_satellite_token(
                    token=token,
                    key_manager=configured_key_manager,
                    audience="syftai-space",
                )

        RSAKeyManager._instance = None


class TestVerifySatelliteTokenForService:
    """Tests for the verify_satellite_token_for_service function."""

    @pytest.fixture
    def mock_user(self):
        """Create a mock user for testing."""
        user = MagicMock()
        user.id = 123
        user.role = "admin"
        user.username = "alice"
        return user

    @pytest.fixture
    def configured_key_manager(self):
        """Create a configured key manager for testing."""
        RSAKeyManager._instance = None
        manager = RSAKeyManager()
        manager._generate_keypair("verify-test-key")
        yield manager
        RSAKeyManager._instance = None

    @pytest.fixture
    def unconfigured_key_manager(self):
        """Create an unconfigured key manager for testing."""
        RSAKeyManager._instance = None
        manager = RSAKeyManager()
        yield manager
        RSAKeyManager._instance = None

    def test_verify_success(self, mock_user, configured_key_manager):
        """Test successful token verification for a service."""
        with patch("syfthub.auth.satellite_tokens.settings") as mock_settings:
            mock_settings.allowed_audiences = {"syftai-space"}
            mock_settings.issuer_url = "https://hub.syft.com"
            mock_settings.satellite_token_expire_seconds = 60

            # Create a token for syftai-space
            token = create_satellite_token(
                user=mock_user,
                audience="syftai-space",
                key_manager=configured_key_manager,
            )

            # Verify as the syftai-space service
            result = verify_satellite_token_for_service(
                token=token,
                key_manager=configured_key_manager,
                authorized_audience="syftai-space",
            )

            assert result.valid is True
            assert result.payload["sub"] == "123"
            assert result.payload["role"] == "admin"
            assert result.payload["aud"] == "syftai-space"
            assert result.error is None
            assert result.message is None

    def test_verify_expired_token(self, mock_user, configured_key_manager):
        """Test verification of expired token."""
        with patch("syfthub.auth.satellite_tokens.settings") as mock_settings:
            mock_settings.allowed_audiences = {"syftai-space"}
            mock_settings.issuer_url = "https://hub.syft.com"
            mock_settings.satellite_token_expire_seconds = -10  # Already expired

            token = create_satellite_token(
                user=mock_user,
                audience="syftai-space",
                key_manager=configured_key_manager,
            )

            result = verify_satellite_token_for_service(
                token=token,
                key_manager=configured_key_manager,
                authorized_audience="syftai-space",
            )

            assert result.valid is False
            assert result.error == "token_expired"
            assert "expired" in result.message.lower()

    def test_verify_audience_mismatch(self, mock_user, configured_key_manager):
        """Test verification fails when audience doesn't match."""
        with patch("syfthub.auth.satellite_tokens.settings") as mock_settings:
            mock_settings.allowed_audiences = {"syftai-space", "other-service"}
            mock_settings.issuer_url = "https://hub.syft.com"
            mock_settings.satellite_token_expire_seconds = 60

            # Create token for syftai-space
            token = create_satellite_token(
                user=mock_user,
                audience="syftai-space",
                key_manager=configured_key_manager,
            )

            # Try to verify as other-service
            result = verify_satellite_token_for_service(
                token=token,
                key_manager=configured_key_manager,
                authorized_audience="other-service",
            )

            assert result.valid is False
            assert result.error == "audience_mismatch"
            assert "syftai-space" in result.message
            assert "other-service" in result.message

    def test_verify_invalid_token_format(self, configured_key_manager):
        """Test verification of malformed token."""
        result = verify_satellite_token_for_service(
            token="not-a-valid-jwt",
            key_manager=configured_key_manager,
            authorized_audience="syftai-space",
        )

        assert result.valid is False
        assert result.error == "invalid_token_format"

    def test_verify_missing_kid(self, configured_key_manager):
        """Test verification of token without kid header."""
        # Create a token manually without kid
        import jwt as pyjwt

        payload = {"sub": "123", "aud": "syftai-space", "iss": "https://hub.syft.com"}
        token = pyjwt.encode(
            payload,
            configured_key_manager.private_key,
            algorithm="RS256",
            # No headers with kid
        )

        with patch("syfthub.auth.satellite_tokens.settings") as mock_settings:
            mock_settings.issuer_url = "https://hub.syft.com"

            result = verify_satellite_token_for_service(
                token=token,
                key_manager=configured_key_manager,
                authorized_audience="syftai-space",
            )

            assert result.valid is False
            assert result.error == "missing_kid"

    def test_verify_unknown_kid(self, mock_user, configured_key_manager):
        """Test verification of token with unknown key ID."""
        # Create a token with different key manager
        RSAKeyManager._instance = None
        other_manager = RSAKeyManager()
        other_manager._generate_keypair("other-key-id")

        with patch("syfthub.auth.satellite_tokens.settings") as mock_settings:
            mock_settings.allowed_audiences = {"syftai-space"}
            mock_settings.issuer_url = "https://hub.syft.com"
            mock_settings.satellite_token_expire_seconds = 60

            token = create_satellite_token(
                user=mock_user,
                audience="syftai-space",
                key_manager=other_manager,
            )

            # Verify with different key manager
            result = verify_satellite_token_for_service(
                token=token,
                key_manager=configured_key_manager,
                authorized_audience="syftai-space",
            )

            assert result.valid is False
            assert result.error == "unknown_key"
            assert "other-key-id" in result.message

        RSAKeyManager._instance = None

    def test_verify_unconfigured_key_manager(self, unconfigured_key_manager):
        """Test verification with unconfigured key manager."""
        result = verify_satellite_token_for_service(
            token="any-token",
            key_manager=unconfigured_key_manager,
            authorized_audience="syftai-space",
        )

        assert result.valid is False
        assert result.error == "idp_not_configured"

    def test_token_verification_result_class(self):
        """Test TokenVerificationResult class."""
        # Success result
        success = TokenVerificationResult(
            valid=True,
            payload={"sub": "123", "role": "admin"},
        )
        assert success.valid is True
        assert success.payload["sub"] == "123"
        assert success.error is None

        # Error result
        error = TokenVerificationResult(
            valid=False,
            error="token_expired",
            message="The token has expired.",
        )
        assert error.valid is False
        assert error.payload == {}
        assert error.error == "token_expired"
        assert error.message == "The token has expired."
