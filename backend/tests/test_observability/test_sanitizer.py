"""Tests for the observability sanitizer module."""

import pytest

from syfthub.observability.sanitizer import (
    _is_sensitive_field,
    sanitize,
    sanitize_headers,
    truncate_body,
)
from syfthub.observability.constants import REDACTED_VALUE


class TestIsSensitiveField:
    """Tests for _is_sensitive_field function."""

    def test_exact_match_sensitive_field(self):
        """Test that exact matches are detected."""
        assert _is_sensitive_field("password") is True
        assert _is_sensitive_field("token") is True
        assert _is_sensitive_field("api_key") is True
        assert _is_sensitive_field("secret") is True
        assert _is_sensitive_field("authorization") is True

    def test_case_insensitive_match(self):
        """Test that matching is case-insensitive."""
        assert _is_sensitive_field("PASSWORD") is True
        assert _is_sensitive_field("Password") is True
        assert _is_sensitive_field("TOKEN") is True
        assert _is_sensitive_field("Api_Key") is True

    def test_pattern_match(self):
        """Test that pattern matching works for sensitive fields."""
        assert _is_sensitive_field("user_password") is True
        assert _is_sensitive_field("my_secret_value") is True
        assert _is_sensitive_field("auth_token") is True
        assert _is_sensitive_field("api_key_id") is True
        assert _is_sensitive_field("credential_file") is True

    def test_non_sensitive_field(self):
        """Test that non-sensitive fields are not flagged."""
        assert _is_sensitive_field("username") is False
        assert _is_sensitive_field("email") is False
        assert _is_sensitive_field("id") is False
        assert _is_sensitive_field("name") is False
        assert _is_sensitive_field("count") is False


class TestSanitize:
    """Tests for sanitize function."""

    def test_sanitize_dict_with_sensitive_fields(self):
        """Test sanitization of dictionary with sensitive fields."""
        data = {
            "username": "john",
            "password": "secret123",
            "email": "john@example.com",
        }
        result = sanitize(data)
        assert result["username"] == "john"
        assert result["password"] == REDACTED_VALUE
        assert result["email"] == "john@example.com"

    def test_sanitize_nested_dict(self):
        """Test sanitization of nested dictionaries."""
        data = {
            "user": {
                "name": "john",
                "info": {
                    "password": "secret123",
                    "email": "john@example.com",
                },
            },
        }
        result = sanitize(data)
        assert result["user"]["name"] == "john"
        assert result["user"]["info"]["password"] == REDACTED_VALUE
        assert result["user"]["info"]["email"] == "john@example.com"

    def test_sanitize_list(self):
        """Test sanitization of lists."""
        data = [
            {"username": "john", "password": "pass1"},
            {"username": "jane", "password": "pass2"},
        ]
        result = sanitize(data)
        assert result[0]["username"] == "john"
        assert result[0]["password"] == REDACTED_VALUE
        assert result[1]["username"] == "jane"
        assert result[1]["password"] == REDACTED_VALUE

    def test_sanitize_tuple(self):
        """Test sanitization of tuples."""
        data = ({"password": "secret"}, {"api_key": "key123"})
        result = sanitize(data)
        assert isinstance(result, tuple)
        assert result[0]["password"] == REDACTED_VALUE
        assert result[1]["api_key"] == REDACTED_VALUE

    def test_sanitize_set(self):
        """Test sanitization of sets."""
        data = {1, 2, 3}
        result = sanitize(data)
        assert isinstance(result, set)
        assert result == {1, 2, 3}

    def test_sanitize_scalars(self):
        """Test that scalar values are returned as-is."""
        assert sanitize("string") == "string"
        assert sanitize(123) == 123
        assert sanitize(45.67) == 45.67
        assert sanitize(True) is True
        assert sanitize(None) is None

    def test_sanitize_max_depth(self):
        """Test that max depth prevents infinite recursion."""
        # Test with max_depth=1: only the top level is processed, nested dicts become REDACTED
        data = {"a": {"b": "value"}}
        result = sanitize(data, max_depth=1)
        assert result["a"] == REDACTED_VALUE

        # Test with higher depth
        data2 = {"a": {"b": {"c": "value"}}}
        result2 = sanitize(data2, max_depth=2)
        assert result2["a"]["b"] == REDACTED_VALUE

        # With enough depth, values are preserved
        result3 = sanitize(data2, max_depth=10)
        assert result3["a"]["b"]["c"] == "value"

    def test_sanitize_max_depth_zero(self):
        """Test that zero max depth returns redacted value."""
        data = {"key": "value"}
        result = sanitize(data, max_depth=0)
        assert result == REDACTED_VALUE


class TestSanitizeHeaders:
    """Tests for sanitize_headers function."""

    def test_sanitize_authorization_header(self):
        """Test that authorization header is redacted."""
        headers = {
            "Authorization": "Bearer abc123",
            "Content-Type": "application/json",
        }
        result = sanitize_headers(headers)
        assert result["Authorization"] == REDACTED_VALUE
        assert result["Content-Type"] == "application/json"

    def test_sanitize_cookie_header(self):
        """Test that cookie header is redacted."""
        headers = {
            "Cookie": "session=abc123",
            "Accept": "application/json",
        }
        result = sanitize_headers(headers)
        assert result["Cookie"] == REDACTED_VALUE
        assert result["Accept"] == "application/json"

    def test_sanitize_api_key_headers(self):
        """Test that API key headers are redacted."""
        headers = {
            "X-API-Key": "secret-key",
            "X-Auth-Token": "auth-token",
            "User-Agent": "test-client",
        }
        result = sanitize_headers(headers)
        assert result["X-API-Key"] == REDACTED_VALUE
        assert result["X-Auth-Token"] == REDACTED_VALUE
        assert result["User-Agent"] == "test-client"

    def test_sanitize_headers_case_insensitive(self):
        """Test that header matching is case-insensitive."""
        headers = {
            "authorization": "Bearer abc123",
            "COOKIE": "session=abc",
        }
        result = sanitize_headers(headers)
        assert result["authorization"] == REDACTED_VALUE
        assert result["COOKIE"] == REDACTED_VALUE


class TestTruncateBody:
    """Tests for truncate_body function."""

    def test_truncate_long_string(self):
        """Test truncation of long strings."""
        long_string = "a" * 2000
        result = truncate_body(long_string, max_length=1000)
        assert len(result) < len(long_string)
        assert "truncated" in result
        assert "2000 total bytes" in result

    def test_short_string_unchanged(self):
        """Test that short strings are not modified."""
        short_string = "short"
        result = truncate_body(short_string, max_length=1000)
        assert result == "short"

    def test_truncate_bytes(self):
        """Test truncation of bytes."""
        large_bytes = b"x" * 2000
        result = truncate_body(large_bytes, max_length=1000)
        assert "binary data" in result
        assert "2000 bytes" in result

    def test_truncate_dict_with_long_values(self):
        """Test truncation of dictionary values."""
        data = {
            "short": "value",
            "long": "x" * 2000,
        }
        result = truncate_body(data, max_length=1000)
        assert result["short"] == "value"
        assert "truncated" in result["long"]

    def test_truncate_long_list(self):
        """Test truncation of long lists."""
        data = list(range(200))
        result = truncate_body(data, max_length=1000)
        assert len(result) == 101  # 100 items + 1 truncation message
        assert "100 more items" in result[-1]

    def test_truncate_short_list(self):
        """Test that short lists are not truncated."""
        data = list(range(10))
        result = truncate_body(data, max_length=1000)
        assert result == list(range(10))

    def test_truncate_non_truncatable_types(self):
        """Test that non-truncatable types are returned as-is."""
        assert truncate_body(123) == 123
        assert truncate_body(45.67) == 45.67
        assert truncate_body(True) is True
        assert truncate_body(None) is None
