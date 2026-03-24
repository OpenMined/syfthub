"""Tests for endpoint schema archived field."""

from datetime import datetime, timezone
from typing import ClassVar

from syfthub.schemas.endpoint import (
    Endpoint,
    EndpointBase,
    EndpointType,
    EndpointUpdate,
    EndpointVisibility,
)


class TestEndpointBaseArchived:
    """Tests for archived field on EndpointBase."""

    def test_archived_defaults_to_false(self):
        """EndpointBase.archived defaults to False when not provided."""
        endpoint = EndpointBase(
            name="Test",
            type=EndpointType.MODEL,
        )
        assert endpoint.archived is False

    def test_archived_can_be_set_true(self):
        """EndpointBase.archived can be explicitly set to True."""
        endpoint = EndpointBase(
            name="Test",
            type=EndpointType.MODEL,
            archived=True,
        )
        assert endpoint.archived is True

    def test_archived_can_be_set_false(self):
        """EndpointBase.archived can be explicitly set to False."""
        endpoint = EndpointBase(
            name="Test",
            type=EndpointType.MODEL,
            archived=False,
        )
        assert endpoint.archived is False


class TestEndpointUpdateArchived:
    """Tests for archived field on EndpointUpdate."""

    def test_archived_defaults_to_none(self):
        """EndpointUpdate.archived defaults to None (not provided)."""
        update = EndpointUpdate()
        assert update.archived is None

    def test_archived_accepts_true(self):
        """EndpointUpdate.archived accepts True."""
        update = EndpointUpdate(archived=True)
        assert update.archived is True

    def test_archived_accepts_false(self):
        """EndpointUpdate.archived accepts False."""
        update = EndpointUpdate(archived=False)
        assert update.archived is False

    def test_archived_is_optional_bool(self):
        """EndpointUpdate allows partial update with only archived."""
        update = EndpointUpdate(archived=True)
        # Other fields should remain None
        assert update.name is None
        assert update.description is None
        assert update.visibility is None


class TestEndpointResponseArchived:
    """Tests for archived field on the full Endpoint response schema."""

    def _make_endpoint(self, **overrides) -> Endpoint:
        """Helper to create a full Endpoint with sensible defaults."""
        now = datetime.now(timezone.utc)
        defaults = {
            "id": 1,
            "user_id": 1,
            "name": "Test",
            "slug": "test-endpoint",
            "description": "A test endpoint",
            "type": EndpointType.MODEL,
            "visibility": EndpointVisibility.PUBLIC,
            "is_active": True,
            "contributors": [],
            "version": "1.0.0",
            "readme": "",
            "tags": [],
            "stars_count": 0,
            "policies": [],
            "connect": [],
            "created_at": now,
            "updated_at": now,
        }
        defaults.update(overrides)
        return Endpoint(**defaults)

    def test_archived_defaults_to_false(self):
        """Endpoint response includes archived=False when not specified."""
        endpoint = self._make_endpoint()
        assert endpoint.archived is False

    def test_archived_true_in_response(self):
        """Endpoint response correctly reflects archived=True."""
        endpoint = self._make_endpoint(archived=True)
        assert endpoint.archived is True

    def test_archived_included_in_model_dump(self):
        """archived field is present in the serialized output."""
        endpoint = self._make_endpoint(archived=True)
        data = endpoint.model_dump()
        assert "archived" in data
        assert data["archived"] is True

    def test_archived_from_attributes(self):
        """Endpoint can be validated from an ORM-like object with archived attribute."""

        class FakeModel:
            """Minimal stand-in for EndpointModel with from_attributes."""

            id = 1
            user_id = 1
            organization_id = None
            name = "Test"
            slug = "test-endpoint"
            description = "A test"
            type = "model"
            visibility = "public"
            is_active = True
            archived = True
            contributors: ClassVar[list] = []
            version = "1.0.0"
            readme = ""
            tags: ClassVar[list] = []
            stars_count = 0
            policies: ClassVar[list] = []
            connect: ClassVar[list] = []
            health_status = None
            health_checked_at = None
            health_ttl_seconds = None
            created_at = datetime.now(timezone.utc)
            updated_at = datetime.now(timezone.utc)

        endpoint = Endpoint.model_validate(FakeModel(), from_attributes=True)
        assert endpoint.archived is True
