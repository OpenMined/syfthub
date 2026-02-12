"""Unit tests for RSA Key Manager.

Tests the key management functionality for the Identity Provider,
including key generation, loading, and JWKS conversion.
"""

import base64
from unittest.mock import patch

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from syfthub.auth.keys import RSAKeyManager, _int_to_base64url
from syfthub.domain.exceptions import KeyNotConfiguredError


class TestBase64URLEncoding:
    """Tests for Base64URL encoding helper function."""

    def test_int_to_base64url_small_number(self):
        """Test encoding small integers."""
        # Standard RSA exponent 65537 should encode to "AQAB"
        result = _int_to_base64url(65537)
        assert result == "AQAB"

    def test_int_to_base64url_large_number(self):
        """Test encoding large integers (like RSA modulus)."""
        # Generate a test number
        large_num = 2**256 - 1
        result = _int_to_base64url(large_num)

        # Should be a non-empty string without padding
        assert isinstance(result, str)
        assert len(result) > 0
        assert "=" not in result  # No padding in Base64URL

    def test_int_to_base64url_no_padding(self):
        """Verify Base64URL output has no padding."""
        # Various numbers that might produce padding in standard Base64
        test_numbers = [1, 255, 65537, 2**128]

        for num in test_numbers:
            result = _int_to_base64url(num)
            assert "=" not in result, f"Number {num} produced padded output"


class TestRSAKeyManager:
    """Tests for RSAKeyManager class."""

    @pytest.fixture
    def fresh_key_manager(self):
        """Create a fresh key manager instance (bypass singleton)."""
        # Reset singleton for testing
        RSAKeyManager._instance = None
        manager = RSAKeyManager()
        yield manager
        # Cleanup
        RSAKeyManager._instance = None

    @pytest.fixture
    def test_keypair(self):
        """Generate a test RSA keypair."""
        private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
        )
        public_key = private_key.public_key()
        return private_key, public_key

    @pytest.fixture
    def test_keypair_pem(self, test_keypair):
        """Get PEM-encoded test keypair."""
        private_key, public_key = test_keypair

        private_pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )

        public_pem = public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )

        return private_pem, public_pem

    def test_singleton_pattern(self):
        """Test that RSAKeyManager follows singleton pattern."""
        # Reset singleton
        RSAKeyManager._instance = None

        manager1 = RSAKeyManager()
        manager2 = RSAKeyManager()

        assert manager1 is manager2

        # Cleanup
        RSAKeyManager._instance = None

    def test_not_configured_initially(self, fresh_key_manager):
        """Test that manager is not configured before initialization."""
        assert not fresh_key_manager.is_configured

    def test_key_not_configured_error(self, fresh_key_manager):
        """Test that accessing unconfigured keys raises error."""
        with pytest.raises(KeyNotConfiguredError):
            _ = fresh_key_manager.private_key

    def test_key_generation(self, fresh_key_manager):
        """Test RSA key auto-generation."""
        fresh_key_manager._generate_keypair("test-key-1")

        assert fresh_key_manager.is_configured
        assert fresh_key_manager.current_key_id == "test-key-1"
        assert fresh_key_manager.private_key is not None
        assert fresh_key_manager.get_public_key("test-key-1") is not None

    def test_load_from_pem_strings(self, fresh_key_manager, test_keypair_pem):
        """Test loading keys from Base64-encoded PEM strings."""
        private_pem, public_pem = test_keypair_pem

        # Encode as Base64 (simulating environment variable format)
        private_b64 = base64.b64encode(private_pem).decode()
        public_b64 = base64.b64encode(public_pem).decode()

        fresh_key_manager._load_from_pem_strings(
            private_b64, public_b64, "loaded-key-1"
        )

        assert fresh_key_manager.is_configured
        assert fresh_key_manager.current_key_id == "loaded-key-1"
        assert fresh_key_manager.get_public_key("loaded-key-1") is not None

    def test_jwks_format(self, fresh_key_manager):
        """Test that JWKS output matches expected format."""
        fresh_key_manager._generate_keypair("jwks-test-key")

        jwks = fresh_key_manager.get_jwks()

        assert "keys" in jwks
        assert len(jwks["keys"]) == 1

        key = jwks["keys"][0]
        assert key["kty"] == "RSA"
        assert key["kid"] == "jwks-test-key"
        assert key["use"] == "sig"
        assert key["alg"] == "RS256"
        assert "n" in key  # Modulus
        assert "e" in key  # Exponent

        # Verify no padding in Base64URL values
        assert "=" not in key["n"]
        assert "=" not in key["e"]

    def test_jwks_multiple_keys(self, fresh_key_manager, test_keypair):
        """Test JWKS with multiple keys (for rotation)."""
        # Generate first key
        fresh_key_manager._generate_keypair("key-1")

        # Add a second key manually
        _, public_key = test_keypair
        fresh_key_manager.add_public_key("key-2", public_key)

        jwks = fresh_key_manager.get_jwks()

        assert len(jwks["keys"]) == 2

        key_ids = {key["kid"] for key in jwks["keys"]}
        assert "key-1" in key_ids
        assert "key-2" in key_ids

    def test_jwks_not_configured_error(self, fresh_key_manager):
        """Test that JWKS raises error when not configured."""
        with pytest.raises(KeyNotConfiguredError):
            fresh_key_manager.get_jwks()

    def test_get_private_key_pem(self, fresh_key_manager):
        """Test exporting private key as PEM."""
        fresh_key_manager._generate_keypair("export-test")

        pem = fresh_key_manager.get_private_key_pem()

        assert pem.startswith(b"-----BEGIN PRIVATE KEY-----")
        assert pem.endswith(b"-----END PRIVATE KEY-----\n")

    def test_get_public_key_pem(self, fresh_key_manager):
        """Test exporting public key as PEM."""
        fresh_key_manager._generate_keypair("export-test")

        pem = fresh_key_manager.get_public_key_pem()

        assert pem.startswith(b"-----BEGIN PUBLIC KEY-----")
        assert pem.endswith(b"-----END PUBLIC KEY-----\n")

    def test_initialize_with_auto_generate(self, fresh_key_manager):
        """Test initialization with auto-generation enabled."""
        with patch("syfthub.auth.keys.settings") as mock_settings:
            mock_settings.rsa_private_key_pem = None
            mock_settings.rsa_public_key_pem = None
            mock_settings.rsa_private_key_path = None
            mock_settings.rsa_public_key_path = None
            mock_settings.auto_generate_rsa_keys = True
            mock_settings.rsa_key_id = "auto-gen-key"
            mock_settings.rsa_key_size = 2048

            fresh_key_manager.initialize()

            assert fresh_key_manager.is_configured
            assert fresh_key_manager.current_key_id == "auto-gen-key"

    def test_initialize_without_keys_or_auto_generate(self, fresh_key_manager):
        """Test initialization with no keys and auto-generation disabled."""
        with patch("syfthub.auth.keys.settings") as mock_settings:
            mock_settings.rsa_private_key_pem = None
            mock_settings.rsa_public_key_pem = None
            mock_settings.rsa_private_key_path = None
            mock_settings.rsa_public_key_path = None
            mock_settings.auto_generate_rsa_keys = False

            fresh_key_manager.initialize()

            # Should initialize but not be configured
            assert not fresh_key_manager.is_configured
