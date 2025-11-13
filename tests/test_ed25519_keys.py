"""Test Ed25519 key generation, regeneration, and signature verification."""

from __future__ import annotations

import base64

import pytest
from fastapi.testclient import TestClient

from syfthub.auth.dependencies import fake_users_db, username_to_id
from syfthub.auth.security import (
    Ed25519KeyPair,
    generate_ed25519_key_pair,
    sign_message_ed25519,
    token_blacklist,
    verify_ed25519_signature,
)
from syfthub.main import app


@pytest.fixture
def client() -> TestClient:
    """Create test client."""
    return TestClient(app)


@pytest.fixture(autouse=True)
def reset_auth_db() -> None:
    """Reset the authentication database before each test."""
    fake_users_db.clear()
    username_to_id.clear()
    token_blacklist.clear()

    # Reset counters
    import syfthub.auth.router as auth_module

    auth_module.user_id_counter = 1


class TestEd25519KeyGeneration:
    """Test Ed25519 key generation utilities."""

    def test_generate_ed25519_key_pair(self) -> None:
        """Test that key pair generation works correctly."""
        key_pair = generate_ed25519_key_pair()

        # Check that key pair is returned
        assert isinstance(key_pair, Ed25519KeyPair)
        assert key_pair.private_key
        assert key_pair.public_key

        # Check that keys are valid base64
        private_key_bytes = base64.b64decode(key_pair.private_key)
        public_key_bytes = base64.b64decode(key_pair.public_key)

        # Ed25519 private key should be 32 bytes
        assert len(private_key_bytes) == 32
        # Ed25519 public key should be 32 bytes
        assert len(public_key_bytes) == 32

    def test_generate_unique_key_pairs(self) -> None:
        """Test that each generated key pair is unique."""
        key_pair1 = generate_ed25519_key_pair()
        key_pair2 = generate_ed25519_key_pair()

        # Keys should be different
        assert key_pair1.private_key != key_pair2.private_key
        assert key_pair1.public_key != key_pair2.public_key

    def test_sign_and_verify_message(self) -> None:
        """Test signing and verifying a message."""
        key_pair = generate_ed25519_key_pair()
        message = "Hello, world!"
        message_bytes = message.encode("utf-8")

        # Sign the message
        signature = sign_message_ed25519(message_bytes, key_pair.private_key)

        # Verify the signature
        is_valid = verify_ed25519_signature(
            message_bytes, signature, key_pair.public_key
        )
        assert is_valid is True

    def test_verify_invalid_signature(self) -> None:
        """Test that invalid signatures are rejected."""
        key_pair = generate_ed25519_key_pair()
        message = "Hello, world!"
        message_bytes = message.encode("utf-8")

        # Create a fake signature
        fake_signature = base64.b64encode(b"fake_signature" + b"0" * 52).decode("utf-8")

        # Verify should fail
        is_valid = verify_ed25519_signature(
            message_bytes, fake_signature, key_pair.public_key
        )
        assert is_valid is False

    def test_verify_wrong_message(self) -> None:
        """Test that signature fails for wrong message."""
        key_pair = generate_ed25519_key_pair()
        original_message = "Hello, world!"
        different_message = "Hello, universe!"

        # Sign original message
        signature = sign_message_ed25519(
            original_message.encode("utf-8"), key_pair.private_key
        )

        # Try to verify with different message
        is_valid = verify_ed25519_signature(
            different_message.encode("utf-8"), signature, key_pair.public_key
        )
        assert is_valid is False

    def test_verify_wrong_public_key(self) -> None:
        """Test that signature fails with wrong public key."""
        key_pair1 = generate_ed25519_key_pair()
        key_pair2 = generate_ed25519_key_pair()
        message = "Hello, world!"
        message_bytes = message.encode("utf-8")

        # Sign with first key
        signature = sign_message_ed25519(message_bytes, key_pair1.private_key)

        # Try to verify with second public key
        is_valid = verify_ed25519_signature(
            message_bytes, signature, key_pair2.public_key
        )
        assert is_valid is False

    def test_verify_malformed_base64(self) -> None:
        """Test that malformed base64 inputs are handled gracefully."""
        key_pair = generate_ed25519_key_pair()
        message = "Hello, world!"
        message_bytes = message.encode("utf-8")

        # Test with invalid base64 signature
        is_valid = verify_ed25519_signature(
            message_bytes, "invalid_base64!", key_pair.public_key
        )
        assert is_valid is False

        # Test with invalid base64 public key
        signature = sign_message_ed25519(message_bytes, key_pair.private_key)
        is_valid = verify_ed25519_signature(message_bytes, signature, "invalid_base64!")
        assert is_valid is False


class TestUserRegistrationWithKeys:
    """Test user registration with Ed25519 key generation."""

    def test_register_user_generates_keys(self, client: TestClient) -> None:
        """Test that user registration generates Ed25519 keys."""
        response = client.post(
            "/api/v1/auth/register",
            json={
                "username": "testuser",
                "email": "test@example.com",
                "full_name": "Test User",
                "password": "testpass123",
                "age": 25,
            },
        )

        assert response.status_code == 201
        data = response.json()

        # Check response structure
        assert "user" in data
        assert "access_token" in data
        assert "refresh_token" in data
        assert "token_type" in data
        assert "keys" in data

        # Check key structure
        keys = data["keys"]
        assert "private_key" in keys
        assert "public_key" in keys
        assert "warning" in keys

        # Verify keys are valid base64
        private_key_bytes = base64.b64decode(keys["private_key"])
        public_key_bytes = base64.b64decode(keys["public_key"])
        assert len(private_key_bytes) == 32
        assert len(public_key_bytes) == 32

        # Check that warning is present
        assert "IMPORTANT" in keys["warning"]
        assert "private key securely" in keys["warning"]

    def test_registered_user_can_sign_and_verify(self, client: TestClient) -> None:
        """Test that registered user can sign messages and verify them."""
        # Register user
        response = client.post(
            "/api/v1/auth/register",
            json={
                "username": "testuser",
                "email": "test@example.com",
                "full_name": "Test User",
                "password": "testpass123",
            },
        )

        assert response.status_code == 201
        keys = response.json()["keys"]

        # Sign a message
        message = "Test message for verification"
        signature = sign_message_ed25519(message.encode("utf-8"), keys["private_key"])

        # Verify the signature through API
        verify_response = client.post(
            "/api/v1/users/verify-signature",
            json={
                "message": message,
                "signature": signature,
                "public_key": keys["public_key"],
            },
        )

        assert verify_response.status_code == 200
        verify_data = verify_response.json()

        assert verify_data["verified"] is True
        assert verify_data["user_info"]["username"] == "testuser"
        assert verify_data["user_info"]["full_name"] == "Test User"
        assert "key_created_at" in verify_data["user_info"]


class TestKeyRegeneration:
    """Test key regeneration functionality."""

    def test_regenerate_keys_requires_authentication(self, client: TestClient) -> None:
        """Test that key regeneration requires authentication."""
        response = client.post("/api/v1/auth/regenerate-keys")
        assert response.status_code == 401

    def test_regenerate_keys_success(self, client: TestClient) -> None:
        """Test successful key regeneration."""
        # Register user first
        register_response = client.post(
            "/api/v1/auth/register",
            json={
                "username": "testuser",
                "email": "test@example.com",
                "full_name": "Test User",
                "password": "testpass123",
            },
        )

        assert register_response.status_code == 201
        register_data = register_response.json()
        old_keys = register_data["keys"]
        access_token = register_data["access_token"]

        # Regenerate keys
        regenerate_response = client.post(
            "/api/v1/auth/regenerate-keys",
            headers={"Authorization": f"Bearer {access_token}"},
        )

        assert regenerate_response.status_code == 200
        regenerate_data = regenerate_response.json()

        # Check response structure
        assert "keys" in regenerate_data
        assert "message" in regenerate_data

        new_keys = regenerate_data["keys"]
        assert "private_key" in new_keys
        assert "public_key" in new_keys
        assert "warning" in new_keys

        # Keys should be different from original
        assert new_keys["private_key"] != old_keys["private_key"]
        assert new_keys["public_key"] != old_keys["public_key"]

        # Check success message
        assert "generated successfully" in regenerate_data["message"]

    def test_old_keys_invalid_after_regeneration(self, client: TestClient) -> None:
        """Test that old keys become invalid after regeneration."""
        # Register user
        register_response = client.post(
            "/api/v1/auth/register",
            json={
                "username": "testuser",
                "email": "test@example.com",
                "full_name": "Test User",
                "password": "testpass123",
            },
        )

        old_keys = register_response.json()["keys"]
        access_token = register_response.json()["access_token"]

        # Sign with old keys
        message = "Test message"
        old_signature = sign_message_ed25519(
            message.encode("utf-8"), old_keys["private_key"]
        )

        # Regenerate keys
        client.post(
            "/api/v1/auth/regenerate-keys",
            headers={"Authorization": f"Bearer {access_token}"},
        )

        # Try to verify with old public key - should fail
        verify_response = client.post(
            "/api/v1/users/verify-signature",
            json={
                "message": message,
                "signature": old_signature,
                "public_key": old_keys["public_key"],
            },
        )

        assert verify_response.status_code == 200
        verify_data = verify_response.json()
        assert verify_data["verified"] is False
        assert verify_data["user_info"] is None
        assert "not found" in verify_data["message"]

    def test_new_keys_work_after_regeneration(self, client: TestClient) -> None:
        """Test that new keys work after regeneration."""
        # Register user
        register_response = client.post(
            "/api/v1/auth/register",
            json={
                "username": "testuser",
                "email": "test@example.com",
                "full_name": "Test User",
                "password": "testpass123",
            },
        )

        access_token = register_response.json()["access_token"]

        # Regenerate keys
        regenerate_response = client.post(
            "/api/v1/auth/regenerate-keys",
            headers={"Authorization": f"Bearer {access_token}"},
        )

        new_keys = regenerate_response.json()["keys"]

        # Sign with new keys
        message = "Test message with new keys"
        new_signature = sign_message_ed25519(
            message.encode("utf-8"), new_keys["private_key"]
        )

        # Verify with new public key - should succeed
        verify_response = client.post(
            "/api/v1/users/verify-signature",
            json={
                "message": message,
                "signature": new_signature,
                "public_key": new_keys["public_key"],
            },
        )

        assert verify_response.status_code == 200
        verify_data = verify_response.json()
        assert verify_data["verified"] is True
        assert verify_data["user_info"]["username"] == "testuser"


class TestSignatureVerification:
    """Test signature verification endpoint."""

    def test_verify_valid_signature(self, client: TestClient) -> None:
        """Test verification of valid signature."""
        # Register user
        register_response = client.post(
            "/api/v1/auth/register",
            json={
                "username": "testuser",
                "email": "test@example.com",
                "full_name": "Test User",
                "password": "testpass123",
            },
        )

        keys = register_response.json()["keys"]

        # Sign a message
        message = "Hello from testuser"
        signature = sign_message_ed25519(message.encode("utf-8"), keys["private_key"])

        # Verify signature
        verify_response = client.post(
            "/api/v1/users/verify-signature",
            json={
                "message": message,
                "signature": signature,
                "public_key": keys["public_key"],
            },
        )

        assert verify_response.status_code == 200
        verify_data = verify_response.json()

        assert verify_data["verified"] is True
        assert verify_data["message"] == "Signature verified successfully"

        user_info = verify_data["user_info"]
        assert user_info["username"] == "testuser"
        assert user_info["full_name"] == "Test User"
        assert user_info["id"] == 1
        assert "key_created_at" in user_info

    def test_verify_invalid_signature(self, client: TestClient) -> None:
        """Test verification of invalid signature."""
        # Register user
        register_response = client.post(
            "/api/v1/auth/register",
            json={
                "username": "testuser",
                "email": "test@example.com",
                "full_name": "Test User",
                "password": "testpass123",
            },
        )

        keys = register_response.json()["keys"]

        # Create fake signature
        fake_signature = base64.b64encode(b"fake" * 16).decode("utf-8")

        # Try to verify fake signature
        verify_response = client.post(
            "/api/v1/users/verify-signature",
            json={
                "message": "Test message",
                "signature": fake_signature,
                "public_key": keys["public_key"],
            },
        )

        assert verify_response.status_code == 200
        verify_data = verify_response.json()

        assert verify_data["verified"] is False
        assert verify_data["user_info"] is None
        assert "Invalid signature" in verify_data["message"]

    def test_verify_unknown_public_key(self, client: TestClient) -> None:
        """Test verification with unknown public key."""
        # Generate a key pair without registering
        unknown_keypair = generate_ed25519_key_pair()

        message = "Test message"
        signature = sign_message_ed25519(
            message.encode("utf-8"), unknown_keypair.private_key
        )

        # Try to verify with unknown public key
        verify_response = client.post(
            "/api/v1/users/verify-signature",
            json={
                "message": message,
                "signature": signature,
                "public_key": unknown_keypair.public_key,
            },
        )

        assert verify_response.status_code == 200
        verify_data = verify_response.json()

        assert verify_data["verified"] is False
        assert verify_data["user_info"] is None
        assert "not found" in verify_data["message"]

    def test_verify_inactive_user(self, client: TestClient) -> None:
        """Test verification with inactive user."""
        # Register user
        register_response = client.post(
            "/api/v1/auth/register",
            json={
                "username": "testuser",
                "email": "test@example.com",
                "full_name": "Test User",
                "password": "testpass123",
            },
        )

        keys = register_response.json()["keys"]

        # Deactivate user
        user_id = 1
        fake_users_db[user_id].is_active = False

        # Sign a message
        message = "Test message"
        signature = sign_message_ed25519(message.encode("utf-8"), keys["private_key"])

        # Try to verify
        verify_response = client.post(
            "/api/v1/users/verify-signature",
            json={
                "message": message,
                "signature": signature,
                "public_key": keys["public_key"],
            },
        )

        assert verify_response.status_code == 200
        verify_data = verify_response.json()

        assert verify_data["verified"] is False
        assert verify_data["user_info"] is None
        assert "inactive" in verify_data["message"]

    def test_verify_missing_fields(self, client: TestClient) -> None:
        """Test verification request with missing fields."""
        # Test missing message
        response = client.post(
            "/api/v1/users/verify-signature",
            json={
                "signature": "test_signature",
                "public_key": "test_public_key",
            },
        )
        assert response.status_code == 422

        # Test missing signature
        response = client.post(
            "/api/v1/users/verify-signature",
            json={
                "message": "test_message",
                "public_key": "test_public_key",
            },
        )
        assert response.status_code == 422

        # Test missing public_key
        response = client.post(
            "/api/v1/users/verify-signature",
            json={
                "message": "test_message",
                "signature": "test_signature",
            },
        )
        assert response.status_code == 422


class TestEdgeCases:
    """Test edge cases and error scenarios."""

    def test_empty_message_signing(self) -> None:
        """Test signing and verifying empty message."""
        key_pair = generate_ed25519_key_pair()
        empty_message = ""
        message_bytes = empty_message.encode("utf-8")

        # Should work with empty message
        signature = sign_message_ed25519(message_bytes, key_pair.private_key)
        is_valid = verify_ed25519_signature(
            message_bytes, signature, key_pair.public_key
        )
        assert is_valid is True

    def test_unicode_message_signing(self) -> None:
        """Test signing and verifying unicode message."""
        key_pair = generate_ed25519_key_pair()
        unicode_message = "Hello, 世界! 🌍"
        message_bytes = unicode_message.encode("utf-8")

        signature = sign_message_ed25519(message_bytes, key_pair.private_key)
        is_valid = verify_ed25519_signature(
            message_bytes, signature, key_pair.public_key
        )
        assert is_valid is True

    def test_large_message_signing(self) -> None:
        """Test signing and verifying large message."""
        key_pair = generate_ed25519_key_pair()
        large_message = "x" * 10000  # 10KB message
        message_bytes = large_message.encode("utf-8")

        signature = sign_message_ed25519(message_bytes, key_pair.private_key)
        is_valid = verify_ed25519_signature(
            message_bytes, signature, key_pair.public_key
        )
        assert is_valid is True

    def test_multiple_regenerations(self, client: TestClient) -> None:
        """Test multiple key regenerations in sequence."""
        # Register user
        register_response = client.post(
            "/api/v1/auth/register",
            json={
                "username": "testuser",
                "email": "test@example.com",
                "full_name": "Test User",
                "password": "testpass123",
            },
        )

        access_token = register_response.json()["access_token"]

        # Regenerate keys multiple times
        previous_keys = []
        for _i in range(3):
            response = client.post(
                "/api/v1/auth/regenerate-keys",
                headers={"Authorization": f"Bearer {access_token}"},
            )

            assert response.status_code == 200
            current_keys = response.json()["keys"]

            # Each generation should produce unique keys
            for prev_keys in previous_keys:
                assert current_keys["private_key"] != prev_keys["private_key"]
                assert current_keys["public_key"] != prev_keys["public_key"]

            previous_keys.append(current_keys)
