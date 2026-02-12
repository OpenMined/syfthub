"""Tests for API token schemas."""

from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from syfthub.schemas.api_token import (
    APIToken,
    APITokenCreate,
    APITokenCreateResponse,
    APITokenListResponse,
    APITokenScope,
    APITokenUpdate,
)


class TestAPITokenScope:
    """Tests for APITokenScope enum."""

    def test_scope_values(self):
        """Test that scope enum has expected values."""
        assert APITokenScope.READ.value == "read"
        assert APITokenScope.WRITE.value == "write"
        assert APITokenScope.FULL.value == "full"

    def test_scope_from_string(self):
        """Test creating scope from string value."""
        assert APITokenScope("read") == APITokenScope.READ
        assert APITokenScope("write") == APITokenScope.WRITE
        assert APITokenScope("full") == APITokenScope.FULL


class TestAPITokenCreate:
    """Tests for APITokenCreate schema."""

    def test_create_minimal(self):
        """Test creating token with minimal data."""
        token = APITokenCreate(name="Test Token")
        assert token.name == "Test Token"
        assert token.scopes == [APITokenScope.FULL]  # Default
        assert token.expires_at is None

    def test_create_with_scopes(self):
        """Test creating token with custom scopes."""
        token = APITokenCreate(name="Test Token", scopes=[APITokenScope.READ])
        assert token.scopes == [APITokenScope.READ]

    def test_create_with_expiration(self):
        """Test creating token with expiration."""
        future = datetime.now(timezone.utc) + timedelta(days=30)
        token = APITokenCreate(name="Test Token", expires_at=future)
        assert token.expires_at is not None

    def test_create_name_validation_min_length(self):
        """Test name minimum length validation."""
        with pytest.raises(ValidationError) as exc_info:
            APITokenCreate(name="")
        assert "String should have at least 1 character" in str(exc_info.value)

    def test_create_name_validation_max_length(self):
        """Test name maximum length validation."""
        with pytest.raises(ValidationError) as exc_info:
            APITokenCreate(name="x" * 101)
        assert "String should have at most 100 characters" in str(exc_info.value)

    def test_create_scopes_empty_validation(self):
        """Test that empty scopes list is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            APITokenCreate(name="Test", scopes=[])
        assert "At least one scope must be specified" in str(exc_info.value)

    def test_create_scopes_deduplication(self):
        """Test that duplicate scopes are removed."""
        token = APITokenCreate(
            name="Test",
            scopes=[APITokenScope.READ, APITokenScope.READ, APITokenScope.WRITE],
        )
        assert token.scopes == [APITokenScope.READ, APITokenScope.WRITE]

    def test_create_expires_at_past_validation(self):
        """Test that past expiration date is rejected."""
        past = datetime.now(timezone.utc) - timedelta(days=1)
        with pytest.raises(ValidationError) as exc_info:
            APITokenCreate(name="Test", expires_at=past)
        assert "Expiration must be in the future" in str(exc_info.value)

    def test_create_expires_at_naive_datetime(self):
        """Test that naive datetime is handled (assumes UTC)."""
        future = datetime.now(timezone.utc) + timedelta(days=30)  # Naive datetime
        token = APITokenCreate(name="Test", expires_at=future)
        assert token.expires_at.tzinfo is not None


class TestAPITokenUpdate:
    """Tests for APITokenUpdate schema."""

    def test_update_valid(self):
        """Test valid update data."""
        update = APITokenUpdate(name="New Name")
        assert update.name == "New Name"

    def test_update_name_min_length(self):
        """Test name minimum length validation."""
        with pytest.raises(ValidationError):
            APITokenUpdate(name="")

    def test_update_name_max_length(self):
        """Test name maximum length validation."""
        with pytest.raises(ValidationError):
            APITokenUpdate(name="x" * 101)


class TestAPIToken:
    """Tests for APIToken response schema."""

    def test_api_token_valid(self):
        """Test valid API token response."""
        now = datetime.now(timezone.utc)
        token = APIToken(
            id=1,
            name="Test Token",
            token_prefix="syft_pat_aB3d",
            scopes=[APITokenScope.FULL],
            expires_at=None,
            last_used_at=None,
            last_used_ip=None,
            is_active=True,
            created_at=now,
            updated_at=now,
        )
        assert token.id == 1
        assert token.name == "Test Token"
        assert token.is_active is True

    def test_api_token_with_usage_tracking(self):
        """Test API token with usage tracking data."""
        now = datetime.now(timezone.utc)
        token = APIToken(
            id=1,
            name="Test Token",
            token_prefix="syft_pat_aB3d",
            scopes=[APITokenScope.READ],
            expires_at=now + timedelta(days=30),
            last_used_at=now - timedelta(hours=1),
            last_used_ip="192.168.1.1",
            is_active=True,
            created_at=now - timedelta(days=7),
            updated_at=now - timedelta(days=7),
        )
        assert token.last_used_at is not None
        assert token.last_used_ip == "192.168.1.1"


class TestAPITokenCreateResponse:
    """Tests for APITokenCreateResponse schema."""

    def test_create_response_valid(self):
        """Test valid creation response with token."""
        now = datetime.now(timezone.utc)
        response = APITokenCreateResponse(
            id=1,
            name="Test Token",
            token="syft_pat_aB3dE5fG7hI9jK1lM3nO5pQ7rS9tU1vW3xY5z",
            token_prefix="syft_pat_aB3d",
            scopes=[APITokenScope.FULL],
            expires_at=None,
            last_used_at=None,
            last_used_ip=None,
            is_active=True,
            created_at=now,
            updated_at=now,
        )
        assert response.token.startswith("syft_pat_")

    def test_create_response_token_required(self):
        """Test that token field is required."""
        now = datetime.now(timezone.utc)
        with pytest.raises(ValidationError):
            APITokenCreateResponse(
                id=1,
                name="Test Token",
                # token is missing
                token_prefix="syft_pat_aB3d",
                scopes=[APITokenScope.FULL],
                is_active=True,
                created_at=now,
            )

    def test_create_response_empty_token_rejected(self):
        """Test that empty token is rejected by validator."""
        now = datetime.now(timezone.utc)
        with pytest.raises(ValidationError) as exc_info:
            APITokenCreateResponse(
                id=1,
                name="Test Token",
                token="",
                token_prefix="syft_pat_aB3d",
                scopes=[APITokenScope.FULL],
                is_active=True,
                created_at=now,
                updated_at=now,
            )
        assert "Token must be present" in str(exc_info.value)


class TestAPITokenListResponse:
    """Tests for APITokenListResponse schema."""

    def test_list_response_empty(self):
        """Test empty list response."""
        response = APITokenListResponse(tokens=[], total=0)
        assert response.tokens == []
        assert response.total == 0

    def test_list_response_with_tokens(self):
        """Test list response with tokens."""
        now = datetime.now(timezone.utc)
        token = APIToken(
            id=1,
            name="Test Token",
            token_prefix="syft_pat_aB3d",
            scopes=[APITokenScope.FULL],
            expires_at=None,
            last_used_at=None,
            last_used_ip=None,
            is_active=True,
            created_at=now,
            updated_at=now,
        )
        response = APITokenListResponse(tokens=[token], total=1)
        assert len(response.tokens) == 1
        assert response.total == 1
