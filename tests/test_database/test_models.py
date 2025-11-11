"""Tests for database models."""

from datetime import datetime
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from syfthub.database.models import DatasiteModel, ItemModel, UserModel


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
        assert user.is_active is True
        assert isinstance(user.created_at, datetime)
        assert isinstance(user.updated_at, datetime)

    def test_user_unique_constraints(
        self, test_session: Session, sample_user_data: dict
    ):
        """Test user unique constraints on username and email."""
        # Create first user
        user1 = UserModel(**sample_user_data)
        test_session.add(user1)
        test_session.commit()

        # Try to create user with same username
        user2_data = sample_user_data.copy()
        user2_data["email"] = "different@example.com"
        user2 = UserModel(**user2_data)
        test_session.add(user2)

        with pytest.raises(IntegrityError):
            test_session.commit()

        test_session.rollback()

        # Try to create user with same email
        user3_data = sample_user_data.copy()
        user3_data["username"] = "differentuser"
        user3 = UserModel(**user3_data)
        test_session.add(user3)

        with pytest.raises(IntegrityError):
            test_session.commit()

    def test_user_relationships(self, test_session: Session, sample_user_data: dict):
        """Test user relationships with items and datasites."""
        # Create user
        user = UserModel(**sample_user_data)
        test_session.add(user)
        test_session.commit()
        test_session.refresh(user)

        # Create item for user
        item = ItemModel(
            user_id=user.id,
            name="Test Item",
            description="Test description",
            price=Decimal("10.00"),
            is_available=True,
        )
        test_session.add(item)

        # Create datasite for user
        datasite = DatasiteModel(
            user_id=user.id,
            name="Test Datasite",
            slug="test-datasite",
            description="Test description",
            visibility="public",
            is_active=True,
        )
        test_session.add(datasite)
        test_session.commit()

        # Test relationships
        test_session.refresh(user)
        assert len(user.items) == 1
        assert len(user.datasites) == 1
        assert user.items[0].name == "Test Item"
        assert user.datasites[0].name == "Test Datasite"


class TestItemModel:
    """Tests for ItemModel."""

    def test_create_item(
        self, test_session: Session, sample_user_data: dict, sample_item_data: dict
    ):
        """Test creating an item."""
        # Create user first
        user = UserModel(**sample_user_data)
        test_session.add(user)
        test_session.commit()
        test_session.refresh(user)

        # Update item data with user ID
        item_data = sample_item_data.copy()
        item_data["user_id"] = user.id

        # Create item
        item = ItemModel(**item_data)
        test_session.add(item)
        test_session.commit()
        test_session.refresh(item)

        assert item.id is not None
        assert item.user_id == user.id
        assert item.name == "Test Item"
        assert item.description == "A test item"
        assert item.price == Decimal("19.99")
        assert item.is_available is True
        assert item.category == "test"
        assert isinstance(item.created_at, datetime)
        assert isinstance(item.updated_at, datetime)

    def test_item_user_relationship(
        self, test_session: Session, sample_user_data: dict, sample_item_data: dict
    ):
        """Test item-user relationship."""
        # Create user
        user = UserModel(**sample_user_data)
        test_session.add(user)
        test_session.commit()
        test_session.refresh(user)

        # Create item
        item_data = sample_item_data.copy()
        item_data["user_id"] = user.id
        item = ItemModel(**item_data)
        test_session.add(item)
        test_session.commit()
        test_session.refresh(item)

        # Test relationship
        assert item.user.username == "testuser"
        assert item.user.id == user.id

    def test_item_foreign_key_constraint(
        self, test_session: Session, sample_item_data: dict
    ):
        """Test that item requires a valid user_id."""
        # Try to create item with non-existent user_id
        item_data = sample_item_data.copy()
        item_data["user_id"] = 999  # Non-existent user
        item = ItemModel(**item_data)
        test_session.add(item)

        with pytest.raises(IntegrityError):
            test_session.commit()


class TestDatasiteModel:
    """Tests for DatasiteModel."""

    def test_create_datasite(
        self, test_session: Session, sample_user_data: dict, sample_datasite_data: dict
    ):
        """Test creating a datasite."""
        # Create user first
        user = UserModel(**sample_user_data)
        test_session.add(user)
        test_session.commit()
        test_session.refresh(user)

        # Update datasite data with user ID
        datasite_data = sample_datasite_data.copy()
        datasite_data["user_id"] = user.id

        # Create datasite
        datasite = DatasiteModel(**datasite_data)
        test_session.add(datasite)
        test_session.commit()
        test_session.refresh(datasite)

        assert datasite.id is not None
        assert datasite.user_id == user.id
        assert datasite.name == "Test Datasite"
        assert datasite.slug == "test-datasite"
        assert datasite.description == "A test datasite"
        assert datasite.visibility == "public"
        assert datasite.is_active is True
        assert isinstance(datasite.created_at, datetime)
        assert isinstance(datasite.updated_at, datetime)

    def test_datasite_user_relationship(
        self, test_session: Session, sample_user_data: dict, sample_datasite_data: dict
    ):
        """Test datasite-user relationship."""
        # Create user
        user = UserModel(**sample_user_data)
        test_session.add(user)
        test_session.commit()
        test_session.refresh(user)

        # Create datasite
        datasite_data = sample_datasite_data.copy()
        datasite_data["user_id"] = user.id
        datasite = DatasiteModel(**datasite_data)
        test_session.add(datasite)
        test_session.commit()
        test_session.refresh(datasite)

        # Test relationship
        assert datasite.user.username == "testuser"
        assert datasite.user.id == user.id

    def test_datasite_unique_slug_per_user(
        self, test_session: Session, sample_user_data: dict, sample_datasite_data: dict
    ):
        """Test that slug is unique per user (not globally unique)."""
        # Create two users
        user1 = UserModel(**sample_user_data)
        test_session.add(user1)

        user2_data = sample_user_data.copy()
        user2_data["username"] = "testuser2"
        user2_data["email"] = "test2@example.com"
        user2 = UserModel(**user2_data)
        test_session.add(user2)
        test_session.commit()
        test_session.refresh(user1)
        test_session.refresh(user2)

        # Create datasite for user1
        datasite1_data = sample_datasite_data.copy()
        datasite1_data["user_id"] = user1.id
        datasite1 = DatasiteModel(**datasite1_data)
        test_session.add(datasite1)
        test_session.commit()

        # Create datasite for user2 with same slug (should work)
        datasite2_data = sample_datasite_data.copy()
        datasite2_data["user_id"] = user2.id
        datasite2 = DatasiteModel(**datasite2_data)
        test_session.add(datasite2)
        test_session.commit()  # Should not raise error

        # Try to create another datasite for user1 with same slug (should fail)
        datasite3_data = sample_datasite_data.copy()
        datasite3_data["user_id"] = user1.id
        datasite3_data["name"] = "Different Name"
        datasite3 = DatasiteModel(**datasite3_data)
        test_session.add(datasite3)

        with pytest.raises(IntegrityError):
            test_session.commit()

    def test_datasite_foreign_key_constraint(
        self, test_session: Session, sample_datasite_data: dict
    ):
        """Test that datasite requires a valid user_id."""
        # Try to create datasite with non-existent user_id
        datasite_data = sample_datasite_data.copy()
        datasite_data["user_id"] = 999  # Non-existent user
        datasite = DatasiteModel(**datasite_data)
        test_session.add(datasite)

        with pytest.raises(IntegrityError):
            test_session.commit()
