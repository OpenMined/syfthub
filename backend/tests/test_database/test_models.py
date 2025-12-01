"""Tests for database models."""

from datetime import datetime

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from syfthub.models import EndpointModel, UserModel


class TestUserModel:
    """Tests for UserModel."""

    def test_create_user(self, test_session: Session, sample_user_data: dict):
        """Test creating a user."""
        user = UserModel(**sample_user_data)
        test_session.add(user)
        test_session.commit()
        test_session.refresh(user)

        assert user.id is not None
        assert user.username == "testuser"
        assert user.email == "test@example.com"
        assert user.full_name == "Test User"
        assert user.age == 25
        assert user.role == "user"
        assert user.public_key is not None  # New field
        assert user.is_active is True
        assert isinstance(user.created_at, datetime)
        assert isinstance(user.updated_at, datetime)
        assert isinstance(user.key_created_at, datetime)  # New field

    def test_user_unique_constraints(
        self, test_session: Session, sample_user_data: dict
    ):
        """Test user unique constraints on username and email."""
        # Create first user
        user1 = UserModel(**sample_user_data)
        test_session.add(user1)
        test_session.commit()

        from tests.test_utils import generate_unique_test_keys

        # Try to create user with same username (should fail on username, not public_key)
        unique_keys_2 = generate_unique_test_keys()
        user2_data = sample_user_data.copy()
        user2_data["email"] = "different@example.com"
        user2_data["public_key"] = unique_keys_2["public_key"]
        user2 = UserModel(**user2_data)
        test_session.add(user2)

        with pytest.raises(IntegrityError):
            test_session.commit()

        test_session.rollback()

        # Try to create user with same email (should fail on email, not public_key)
        unique_keys_3 = generate_unique_test_keys()
        user3_data = sample_user_data.copy()
        user3_data["username"] = "differentuser"
        user3_data["public_key"] = unique_keys_3["public_key"]
        user3 = UserModel(**user3_data)
        test_session.add(user3)

        with pytest.raises(IntegrityError):
            test_session.commit()

    def test_user_relationships(self, test_session: Session, sample_user_data: dict):
        """Test user relationships with endpoints."""
        # Create user
        user = UserModel(**sample_user_data)
        test_session.add(user)
        test_session.commit()
        test_session.refresh(user)

        # Create endpoint for user
        endpoint = EndpointModel(
            user_id=user.id,
            name="Test Endpoint",
            slug="test-endpoint",
            description="Test description",
            visibility="public",
            is_active=True,
        )
        test_session.add(endpoint)
        test_session.commit()

        # Test relationships
        test_session.refresh(user)
        assert len(user.endpoints) == 1
        assert user.endpoints[0].name == "Test Endpoint"


class TestEndpointModel:
    """Tests for EndpointModel."""

    def test_create_endpoint(
        self, test_session: Session, sample_user_data: dict, sample_endpoint_data: dict
    ):
        """Test creating a endpoint."""
        # Create user first
        user = UserModel(**sample_user_data)
        test_session.add(user)
        test_session.commit()
        test_session.refresh(user)

        # Update endpoint data with user ID
        endpoint_data = sample_endpoint_data.copy()
        endpoint_data["user_id"] = user.id

        # Create endpoint
        endpoint = EndpointModel(**endpoint_data)
        test_session.add(endpoint)
        test_session.commit()
        test_session.refresh(endpoint)

        assert endpoint.id is not None
        assert endpoint.user_id == user.id
        assert endpoint.name == "Test Endpoint"
        assert endpoint.slug == "test-endpoint"
        assert endpoint.description == "A test endpoint"
        assert endpoint.visibility == "public"
        assert endpoint.is_active is True
        assert isinstance(endpoint.created_at, datetime)
        assert isinstance(endpoint.updated_at, datetime)

    def test_endpoint_user_relationship(
        self, test_session: Session, sample_user_data: dict, sample_endpoint_data: dict
    ):
        """Test endpoint-user relationship."""
        # Create user
        user = UserModel(**sample_user_data)
        test_session.add(user)
        test_session.commit()
        test_session.refresh(user)

        # Create endpoint
        endpoint_data = sample_endpoint_data.copy()
        endpoint_data["user_id"] = user.id
        endpoint = EndpointModel(**endpoint_data)
        test_session.add(endpoint)
        test_session.commit()
        test_session.refresh(endpoint)

        # Test relationship
        assert endpoint.user.username == "testuser"
        assert endpoint.user.id == user.id

    def test_endpoint_unique_slug_per_user(
        self, test_session: Session, sample_user_data: dict, sample_endpoint_data: dict
    ):
        """Test that slug is unique per user (not globally unique)."""
        # Create two users
        user1 = UserModel(**sample_user_data)
        test_session.add(user1)

        from tests.test_utils import generate_unique_test_keys

        user2_data = sample_user_data.copy()
        user2_data["username"] = "testuser2"
        user2_data["email"] = "test2@example.com"
        # Generate unique public key for second user
        unique_keys = generate_unique_test_keys()
        user2_data["public_key"] = unique_keys["public_key"]
        user2 = UserModel(**user2_data)
        test_session.add(user2)
        test_session.commit()
        test_session.refresh(user1)
        test_session.refresh(user2)

        # Create endpoint for user1
        endpoint1_data = sample_endpoint_data.copy()
        endpoint1_data["user_id"] = user1.id
        endpoint1 = EndpointModel(**endpoint1_data)
        test_session.add(endpoint1)
        test_session.commit()

        # Create endpoint for user2 with same slug (should work)
        endpoint2_data = sample_endpoint_data.copy()
        endpoint2_data["user_id"] = user2.id
        endpoint2 = EndpointModel(**endpoint2_data)
        test_session.add(endpoint2)
        test_session.commit()  # Should not raise error

        # Try to create another endpoint for user1 with same slug (should fail)
        endpoint3_data = sample_endpoint_data.copy()
        endpoint3_data["user_id"] = user1.id
        endpoint3_data["name"] = "Different Name"
        endpoint3 = EndpointModel(**endpoint3_data)
        test_session.add(endpoint3)

        with pytest.raises(IntegrityError):
            test_session.commit()

    def test_endpoint_foreign_key_constraint(
        self, test_session: Session, sample_endpoint_data: dict
    ):
        """Test that endpoint requires a valid user_id."""
        # Try to create endpoint with non-existent user_id
        endpoint_data = sample_endpoint_data.copy()
        endpoint_data["user_id"] = 999  # Non-existent user
        endpoint = EndpointModel(**endpoint_data)
        test_session.add(endpoint)

        with pytest.raises(IntegrityError):
            test_session.commit()
