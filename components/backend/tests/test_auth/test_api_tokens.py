"""Tests for API token utility functions."""

from syfthub.auth.api_tokens import (
    TOKEN_PREFIX,
    TOKEN_PREFIX_LENGTH,
    generate_api_token,
    get_token_prefix,
    hash_api_token,
    is_api_token,
    mask_token,
    secure_compare,
    verify_api_token_format,
)


class TestGenerateAPIToken:
    """Tests for generate_api_token function."""

    def test_generate_api_token_returns_tuple(self):
        """Test that generate_api_token returns a tuple of 3 strings."""
        result = generate_api_token()
        assert isinstance(result, tuple)
        assert len(result) == 3
        full_token, token_hash, token_prefix = result
        assert isinstance(full_token, str)
        assert isinstance(token_hash, str)
        assert isinstance(token_prefix, str)

    def test_generate_api_token_has_correct_prefix(self):
        """Test that generated token starts with syft_pat_."""
        full_token, _, _ = generate_api_token()
        assert full_token.startswith(TOKEN_PREFIX)

    def test_generate_api_token_hash_is_sha256(self):
        """Test that token hash is 64 characters (SHA-256 hex digest)."""
        _, token_hash, _ = generate_api_token()
        assert len(token_hash) == 64
        # Should be valid hex
        assert all(c in "0123456789abcdef" for c in token_hash)

    def test_generate_api_token_prefix_has_correct_length(self):
        """Test that token prefix has the expected length."""
        _, _, token_prefix = generate_api_token()
        assert len(token_prefix) == TOKEN_PREFIX_LENGTH

    def test_generate_api_token_uniqueness(self):
        """Test that successive calls generate different tokens."""
        tokens = [generate_api_token() for _ in range(10)]
        full_tokens = [t[0] for t in tokens]
        hashes = [t[1] for t in tokens]
        # All tokens should be unique
        assert len(set(full_tokens)) == 10
        assert len(set(hashes)) == 10

    def test_generated_token_passes_format_validation(self):
        """Test that generated tokens pass format validation."""
        full_token, _, _ = generate_api_token()
        assert verify_api_token_format(full_token)


class TestHashAPIToken:
    """Tests for hash_api_token function."""

    def test_hash_api_token_returns_string(self):
        """Test that hash_api_token returns a string."""
        result = hash_api_token("test_token")
        assert isinstance(result, str)

    def test_hash_api_token_returns_sha256(self):
        """Test that hash_api_token returns a 64-char hex string."""
        result = hash_api_token("test_token")
        assert len(result) == 64
        assert all(c in "0123456789abcdef" for c in result)

    def test_hash_api_token_is_deterministic(self):
        """Test that same input produces same hash."""
        token = "syft_pat_test123"
        hash1 = hash_api_token(token)
        hash2 = hash_api_token(token)
        assert hash1 == hash2

    def test_hash_api_token_different_inputs(self):
        """Test that different inputs produce different hashes."""
        hash1 = hash_api_token("token1")
        hash2 = hash_api_token("token2")
        assert hash1 != hash2


class TestGetTokenPrefix:
    """Tests for get_token_prefix function."""

    def test_get_token_prefix_length(self):
        """Test that get_token_prefix returns correct length."""
        token = "syft_pat_aB3dE5fG7hI9jK1lM3nO5pQ7rS9tU1vW3xY5z"
        prefix = get_token_prefix(token)
        assert len(prefix) == TOKEN_PREFIX_LENGTH

    def test_get_token_prefix_content(self):
        """Test that get_token_prefix returns first chars."""
        token = "syft_pat_aB3dE5fG7hI9jK1lM3nO5pQ7rS9tU1vW3xY5z"
        prefix = get_token_prefix(token)
        assert token.startswith(prefix)

    def test_get_token_prefix_short_token(self):
        """Test get_token_prefix with token shorter than prefix length."""
        token = "short"
        prefix = get_token_prefix(token)
        assert prefix == "short"


class TestIsAPIToken:
    """Tests for is_api_token function."""

    def test_is_api_token_with_valid_token(self):
        """Test is_api_token returns True for valid format."""
        assert is_api_token("syft_pat_aB3dE5fG") is True

    def test_is_api_token_with_other_syft_token(self):
        """Test is_api_token returns True for other syft tokens."""
        assert is_api_token("syft_other_test") is True

    def test_is_api_token_with_jwt(self):
        """Test is_api_token returns False for JWT tokens."""
        jwt = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.test"
        assert is_api_token(jwt) is False

    def test_is_api_token_with_random_string(self):
        """Test is_api_token returns False for random strings."""
        assert is_api_token("random_string") is False

    def test_is_api_token_empty_string(self):
        """Test is_api_token returns False for empty string."""
        assert is_api_token("") is False


class TestVerifyAPITokenFormat:
    """Tests for verify_api_token_format function."""

    def test_verify_valid_format(self):
        """Test verify_api_token_format with valid token."""
        # Generate a real token to ensure proper format
        token, _, _ = generate_api_token()
        assert verify_api_token_format(token) is True

    def test_verify_invalid_prefix(self):
        """Test verify_api_token_format with wrong prefix."""
        assert (
            verify_api_token_format(
                "invalid_prefix_aB3dE5fG7hI9jK1lM3nO5pQ7rS9tU1vW3xY5z"
            )
            is False
        )

    def test_verify_too_short(self):
        """Test verify_api_token_format with too short token."""
        assert verify_api_token_format("syft_pat_short") is False

    def test_verify_invalid_characters(self):
        """Test verify_api_token_format with invalid characters."""
        # @ is not a valid base64url character
        assert (
            verify_api_token_format("syft_pat_@B3dE5fG7hI9jK1lM3nO5pQ7rS9tU1vW3xY5z")
            is False
        )

    def test_verify_empty_string(self):
        """Test verify_api_token_format with empty string."""
        assert verify_api_token_format("") is False


class TestSecureCompare:
    """Tests for secure_compare function."""

    def test_secure_compare_equal_strings(self):
        """Test secure_compare returns True for equal strings."""
        assert secure_compare("test123", "test123") is True

    def test_secure_compare_different_strings(self):
        """Test secure_compare returns False for different strings."""
        assert secure_compare("test123", "test456") is False

    def test_secure_compare_empty_strings(self):
        """Test secure_compare with empty strings."""
        assert secure_compare("", "") is True

    def test_secure_compare_different_lengths(self):
        """Test secure_compare with different length strings."""
        assert secure_compare("short", "longer_string") is False


class TestMaskToken:
    """Tests for mask_token function."""

    def test_mask_token_normal(self):
        """Test mask_token with normal token."""
        token = "syft_pat_aB3dE5fG7hI9jK1lM3nO5pQ7rS9tU1vW3xY5z"
        masked = mask_token(token)
        assert masked.endswith("****")
        assert len(masked) == TOKEN_PREFIX_LENGTH
        assert "aB3d" not in masked or masked.startswith("syft_pat_aB")

    def test_mask_token_preserves_prefix_info(self):
        """Test mask_token preserves identifying info."""
        token = "syft_pat_aB3dE5fG7hI9jK1lM3nO5pQ7rS9tU1vW3xY5z"
        masked = mask_token(token)
        # Should start with syft_pat_
        assert masked.startswith("syft_pat_")

    def test_mask_token_short_input(self):
        """Test mask_token with input shorter than prefix length."""
        token = "short"
        masked = mask_token(token)
        assert masked == "short"

    def test_mask_token_exact_prefix_length(self):
        """Test mask_token with input exactly prefix length."""
        token = "syft_pat_aB3dE5f"  # 16 chars
        masked = mask_token(token)
        assert masked == token
