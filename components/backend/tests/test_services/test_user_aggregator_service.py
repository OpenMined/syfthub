"""Tests for UserAggregatorService."""

import pytest
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from syfthub.models.user import UserModel
from syfthub.models.user_aggregator import UserAggregatorModel
from syfthub.schemas.user import (
    UserAggregatorCreate,
    UserAggregatorUpdate,
)
from syfthub.services.user_aggregator_service import UserAggregatorService


class TestUserAggregatorServiceGetUserAggregators:
    """Tests for get_user_aggregators method."""

    def test_get_empty_list_when_no_aggregators(self, test_session: Session):
        """Test returns empty list when user has no aggregators."""
        service = UserAggregatorService(test_session)
        result = service.get_user_aggregators(1)

        assert result.aggregators == []
        assert result.default_aggregator_id is None

    def test_get_aggregators_with_default_marked(self, test_session: Session):
        """Test returns aggregators with default marked."""
        service = UserAggregatorService(test_session)

        # Create user
        user = UserModel(
            username="testuser",
            email="test@example.com",
            full_name="Test User",
            password_hash="hashed",
            is_active=True,
        )
        test_session.add(user)
        test_session.commit()
        test_session.refresh(user)

        # Create aggregators
        agg1 = UserAggregatorModel(
            user_id=user.id,
            name="First Aggregator",
            url="https://first.example.com",
            is_default=False,
        )
        agg2 = UserAggregatorModel(
            user_id=user.id,
            name="Default Aggregator",
            url="https://default.example.com",
            is_default=True,
        )
        test_session.add_all([agg1, agg2])
        test_session.commit()
        test_session.refresh(agg2)

        result = service.get_user_aggregators(user.id)

        assert len(result.aggregators) == 2
        assert result.default_aggregator_id == agg2.id

    def test_get_aggregators_no_default(self, test_session: Session):
        """Test returns None for default_aggregator_id when no default."""
        service = UserAggregatorService(test_session)

        # Create user
        user = UserModel(
            username="testuser",
            email="test@example.com",
            full_name="Test User",
            password_hash="hashed",
            is_active=True,
        )
        test_session.add(user)
        test_session.commit()
        test_session.refresh(user)

        # Create non-default aggregators
        agg = UserAggregatorModel(
            user_id=user.id,
            name="Non-default Aggregator",
            url="https://example.com",
            is_default=False,
        )
        test_session.add(agg)
        test_session.commit()

        result = service.get_user_aggregators(user.id)

        assert len(result.aggregators) == 1
        assert result.default_aggregator_id is None


class TestUserAggregatorServiceGetAggregator:
    """Tests for get_aggregator method."""

    def test_get_aggregator_success(self, test_session: Session):
        """Test successful aggregator retrieval."""
        service = UserAggregatorService(test_session)

        # Create user and aggregator
        user = UserModel(
            username="testuser",
            email="test@example.com",
            full_name="Test User",
            password_hash="hashed",
            is_active=True,
        )
        test_session.add(user)
        test_session.commit()
        test_session.refresh(user)

        agg = UserAggregatorModel(
            user_id=user.id,
            name="Test Aggregator",
            url="https://example.com",
            is_default=False,
        )
        test_session.add(agg)
        test_session.commit()
        test_session.refresh(agg)

        result = service.get_aggregator(agg.id, user.id)

        assert result.name == "Test Aggregator"
        assert result.url == "https://example.com"

    def test_get_aggregator_not_found(self, test_session: Session):
        """Test 404 when aggregator not found."""
        service = UserAggregatorService(test_session)

        with pytest.raises(HTTPException) as exc_info:
            service.get_aggregator(99999, 1)

        assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND
        assert "not found" in str(exc_info.value.detail).lower()

    def test_get_aggregator_wrong_user(self, test_session: Session):
        """Test 403 when aggregator belongs to different user."""
        service = UserAggregatorService(test_session)

        # Create two users
        user1 = UserModel(
            username="user1",
            email="user1@example.com",
            full_name="User 1",
            password_hash="hashed",
            is_active=True,
        )
        user2 = UserModel(
            username="user2",
            email="user2@example.com",
            full_name="User 2",
            password_hash="hashed",
            is_active=True,
        )
        test_session.add_all([user1, user2])
        test_session.commit()
        test_session.refresh(user1)
        test_session.refresh(user2)

        # Create aggregator for user1
        agg = UserAggregatorModel(
            user_id=user1.id,
            name="User1 Aggregator",
            url="https://example.com",
            is_default=False,
        )
        test_session.add(agg)
        test_session.commit()
        test_session.refresh(agg)

        # Try to access with user2
        with pytest.raises(HTTPException) as exc_info:
            service.get_aggregator(agg.id, user2.id)

        assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
        assert "permission denied" in str(exc_info.value.detail).lower()


class TestUserAggregatorServiceCreateAggregator:
    """Tests for create_aggregator method."""

    def test_create_first_aggregator_becomes_default(self, test_session: Session):
        """Test first aggregator is automatically set as default."""
        service = UserAggregatorService(test_session)

        # Create user
        user = UserModel(
            username="testuser",
            email="test@example.com",
            full_name="Test User",
            password_hash="hashed",
            is_active=True,
        )
        test_session.add(user)
        test_session.commit()
        test_session.refresh(user)

        # Create aggregator with is_default=False (should be forced to True)
        data = UserAggregatorCreate(
            name="New Aggregator",
            url="https://example.com",
            is_default=False,
        )
        result = service.create_aggregator(user.id, data)

        assert result.is_default is True

    def test_create_additional_aggregator_does_not_auto_default(
        self, test_session: Session
    ):
        """Test additional aggregator respects is_default=False."""
        service = UserAggregatorService(test_session)

        # Create user and first aggregator
        user = UserModel(
            username="testuser",
            email="test@example.com",
            full_name="Test User",
            password_hash="hashed",
            is_active=True,
        )
        test_session.add(user)
        test_session.commit()
        test_session.refresh(user)

        agg1 = UserAggregatorModel(
            user_id=user.id,
            name="Default Aggregator",
            url="https://default.example.com",
            is_default=True,
        )
        test_session.add(agg1)
        test_session.commit()

        # Create second aggregator with is_default=False
        data = UserAggregatorCreate(
            name="Second Aggregator",
            url="https://second.example.com",
            is_default=False,
        )
        result = service.create_aggregator(user.id, data)

        assert result.is_default is False

    def test_create_aggregator_switches_default(self, test_session: Session):
        """Test creating with is_default=True switches default."""
        service = UserAggregatorService(test_session)

        # Create user and first aggregator
        user = UserModel(
            username="testuser",
            email="test@example.com",
            full_name="Test User",
            password_hash="hashed",
            is_active=True,
        )
        test_session.add(user)
        test_session.commit()
        test_session.refresh(user)

        agg1 = UserAggregatorModel(
            user_id=user.id,
            name="Old Default",
            url="https://old.example.com",
            is_default=True,
        )
        test_session.add(agg1)
        test_session.commit()

        # Create new aggregator with is_default=True
        data = UserAggregatorCreate(
            name="New Default",
            url="https://new.example.com",
            is_default=True,
        )
        result = service.create_aggregator(user.id, data)

        assert result.is_default is True

        # Verify old default is no longer default
        test_session.refresh(agg1)
        assert agg1.is_default is False


class TestUserAggregatorServiceUpdateAggregator:
    """Tests for update_aggregator method."""

    def test_update_name_and_url(self, test_session: Session):
        """Test updating name and URL."""
        service = UserAggregatorService(test_session)

        # Create user and aggregator
        user = UserModel(
            username="testuser",
            email="test@example.com",
            full_name="Test User",
            password_hash="hashed",
            is_active=True,
        )
        test_session.add(user)
        test_session.commit()
        test_session.refresh(user)

        agg = UserAggregatorModel(
            user_id=user.id,
            name="Original",
            url="https://original.example.com",
            is_default=False,
        )
        test_session.add(agg)
        test_session.commit()
        test_session.refresh(agg)

        # Update
        data = UserAggregatorUpdate(
            name="Updated",
            url="https://updated.example.com",
        )
        result = service.update_aggregator(agg.id, user.id, data)

        assert result.name == "Updated"
        assert result.url == "https://updated.example.com"

    def test_update_switches_default(self, test_session: Session):
        """Test updating with is_default=True switches default."""
        service = UserAggregatorService(test_session)

        # Create user and aggregators
        user = UserModel(
            username="testuser",
            email="test@example.com",
            full_name="Test User",
            password_hash="hashed",
            is_active=True,
        )
        test_session.add(user)
        test_session.commit()
        test_session.refresh(user)

        agg1 = UserAggregatorModel(
            user_id=user.id,
            name="Old Default",
            url="https://old.example.com",
            is_default=True,
        )
        agg2 = UserAggregatorModel(
            user_id=user.id,
            name="Not Default",
            url="https://not.example.com",
            is_default=False,
        )
        test_session.add_all([agg1, agg2])
        test_session.commit()
        test_session.refresh(agg1)
        test_session.refresh(agg2)

        # Update agg2 to be default
        data = UserAggregatorUpdate(is_default=True)
        result = service.update_aggregator(agg2.id, user.id, data)

        assert result.is_default is True

        # Verify old default is no longer default
        test_session.refresh(agg1)
        assert agg1.is_default is False

    def test_update_not_found(self, test_session: Session):
        """Test 404 when aggregator not found."""
        service = UserAggregatorService(test_session)

        data = UserAggregatorUpdate(name="New Name")
        with pytest.raises(HTTPException) as exc_info:
            service.update_aggregator(99999, 1, data)

        assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND

    def test_update_wrong_user(self, test_session: Session):
        """Test 403 when aggregator belongs to different user."""
        service = UserAggregatorService(test_session)

        # Create two users
        user1 = UserModel(
            username="user1",
            email="user1@example.com",
            full_name="User 1",
            password_hash="hashed",
            is_active=True,
        )
        user2 = UserModel(
            username="user2",
            email="user2@example.com",
            full_name="User 2",
            password_hash="hashed",
            is_active=True,
        )
        test_session.add_all([user1, user2])
        test_session.commit()
        test_session.refresh(user1)
        test_session.refresh(user2)

        # Create aggregator for user1
        agg = UserAggregatorModel(
            user_id=user1.id,
            name="User1 Aggregator",
            url="https://example.com",
            is_default=False,
        )
        test_session.add(agg)
        test_session.commit()
        test_session.refresh(agg)

        # Try to update with user2
        data = UserAggregatorUpdate(name="Hacked Name")
        with pytest.raises(HTTPException) as exc_info:
            service.update_aggregator(agg.id, user2.id, data)

        assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN


class TestUserAggregatorServiceDeleteAggregator:
    """Tests for delete_aggregator method."""

    def test_delete_non_default_aggregator(self, test_session: Session):
        """Test deleting a non-default aggregator."""
        service = UserAggregatorService(test_session)

        # Create user and aggregator
        user = UserModel(
            username="testuser",
            email="test@example.com",
            full_name="Test User",
            password_hash="hashed",
            is_active=True,
        )
        test_session.add(user)
        test_session.commit()
        test_session.refresh(user)

        agg = UserAggregatorModel(
            user_id=user.id,
            name="To Delete",
            url="https://delete.example.com",
            is_default=False,
        )
        test_session.add(agg)
        test_session.commit()
        test_session.refresh(agg)

        # Delete
        service.delete_aggregator(agg.id, user.id)

        # Verify deleted
        deleted = service.aggregator_repository.get_by_id(agg.id)
        assert deleted is None

    def test_delete_default_aggregator_promotes_another(self, test_session: Session):
        """Test deleting default promotes another aggregator to default."""
        service = UserAggregatorService(test_session)

        # Create user and aggregators
        user = UserModel(
            username="testuser",
            email="test@example.com",
            full_name="Test User",
            password_hash="hashed",
            is_active=True,
        )
        test_session.add(user)
        test_session.commit()
        test_session.refresh(user)

        agg1 = UserAggregatorModel(
            user_id=user.id,
            name="Default To Delete",
            url="https://default.example.com",
            is_default=True,
        )
        agg2 = UserAggregatorModel(
            user_id=user.id,
            name="Should Become Default",
            url="https://second.example.com",
            is_default=False,
        )
        test_session.add_all([agg1, agg2])
        test_session.commit()
        test_session.refresh(agg1)
        test_session.refresh(agg2)

        # Delete default
        service.delete_aggregator(agg1.id, user.id)

        # Verify agg2 is now default
        test_session.refresh(agg2)
        assert agg2.is_default is True

    def test_delete_last_aggregator_no_promotion(self, test_session: Session):
        """Test deleting last aggregator does not cause errors."""
        service = UserAggregatorService(test_session)

        # Create user and single aggregator
        user = UserModel(
            username="testuser",
            email="test@example.com",
            full_name="Test User",
            password_hash="hashed",
            is_active=True,
        )
        test_session.add(user)
        test_session.commit()
        test_session.refresh(user)

        agg = UserAggregatorModel(
            user_id=user.id,
            name="Only Aggregator",
            url="https://only.example.com",
            is_default=True,
        )
        test_session.add(agg)
        test_session.commit()
        test_session.refresh(agg)

        # Delete
        service.delete_aggregator(agg.id, user.id)

        # Verify no errors and no aggregators remain
        remaining = service.aggregator_repository.get_by_user_id(user.id)
        assert remaining == []

    def test_delete_not_found(self, test_session: Session):
        """Test 404 when aggregator not found."""
        service = UserAggregatorService(test_session)

        with pytest.raises(HTTPException) as exc_info:
            service.delete_aggregator(99999, 1)

        assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND

    def test_delete_wrong_user(self, test_session: Session):
        """Test 403 when aggregator belongs to different user."""
        service = UserAggregatorService(test_session)

        # Create two users
        user1 = UserModel(
            username="user1",
            email="user1@example.com",
            full_name="User 1",
            password_hash="hashed",
            is_active=True,
        )
        user2 = UserModel(
            username="user2",
            email="user2@example.com",
            full_name="User 2",
            password_hash="hashed",
            is_active=True,
        )
        test_session.add_all([user1, user2])
        test_session.commit()
        test_session.refresh(user1)
        test_session.refresh(user2)

        # Create aggregator for user1
        agg = UserAggregatorModel(
            user_id=user1.id,
            name="User1 Aggregator",
            url="https://example.com",
            is_default=False,
        )
        test_session.add(agg)
        test_session.commit()
        test_session.refresh(agg)

        # Try to delete with user2
        with pytest.raises(HTTPException) as exc_info:
            service.delete_aggregator(agg.id, user2.id)

        assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN


class TestUserAggregatorServiceSetDefaultAggregator:
    """Tests for set_default_aggregator method."""

    def test_set_default_success(self, test_session: Session):
        """Test successfully setting an aggregator as default."""
        service = UserAggregatorService(test_session)

        # Create user and aggregators
        user = UserModel(
            username="testuser",
            email="test@example.com",
            full_name="Test User",
            password_hash="hashed",
            is_active=True,
        )
        test_session.add(user)
        test_session.commit()
        test_session.refresh(user)

        agg1 = UserAggregatorModel(
            user_id=user.id,
            name="Old Default",
            url="https://old.example.com",
            is_default=True,
        )
        agg2 = UserAggregatorModel(
            user_id=user.id,
            name="New Default",
            url="https://new.example.com",
            is_default=False,
        )
        test_session.add_all([agg1, agg2])
        test_session.commit()
        test_session.refresh(agg1)
        test_session.refresh(agg2)

        # Set agg2 as default
        result = service.set_default_aggregator(agg2.id, user.id)

        assert result.is_default is True

        # Verify old default is no longer default
        test_session.refresh(agg1)
        assert agg1.is_default is False

    def test_set_default_not_found(self, test_session: Session):
        """Test 404 when aggregator not found."""
        service = UserAggregatorService(test_session)

        with pytest.raises(HTTPException) as exc_info:
            service.set_default_aggregator(99999, 1)

        assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND

    def test_set_default_wrong_user(self, test_session: Session):
        """Test 403 when aggregator belongs to different user."""
        service = UserAggregatorService(test_session)

        # Create two users
        user1 = UserModel(
            username="user1",
            email="user1@example.com",
            full_name="User 1",
            password_hash="hashed",
            is_active=True,
        )
        user2 = UserModel(
            username="user2",
            email="user2@example.com",
            full_name="User 2",
            password_hash="hashed",
            is_active=True,
        )
        test_session.add_all([user1, user2])
        test_session.commit()
        test_session.refresh(user1)
        test_session.refresh(user2)

        # Create aggregator for user1
        agg = UserAggregatorModel(
            user_id=user1.id,
            name="User1 Aggregator",
            url="https://example.com",
            is_default=False,
        )
        test_session.add(agg)
        test_session.commit()
        test_session.refresh(agg)

        # Try to set default with user2
        with pytest.raises(HTTPException) as exc_info:
            service.set_default_aggregator(agg.id, user2.id)

        assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN


class TestUserAggregatorServiceGetDefaultAggregatorUrl:
    """Tests for get_default_aggregator_url method."""

    def test_get_default_url_when_exists(self, test_session: Session):
        """Test returns URL when default aggregator exists."""
        service = UserAggregatorService(test_session)

        # Create user and default aggregator
        user = UserModel(
            username="testuser",
            email="test@example.com",
            full_name="Test User",
            password_hash="hashed",
            is_active=True,
        )
        test_session.add(user)
        test_session.commit()
        test_session.refresh(user)

        agg = UserAggregatorModel(
            user_id=user.id,
            name="Default",
            url="https://default.example.com",
            is_default=True,
        )
        test_session.add(agg)
        test_session.commit()

        result = service.get_default_aggregator_url(user.id)

        assert result == "https://default.example.com"

    def test_get_default_url_when_no_default(self, test_session: Session):
        """Test returns None when no default aggregator."""
        service = UserAggregatorService(test_session)

        # Create user and non-default aggregator
        user = UserModel(
            username="testuser",
            email="test@example.com",
            full_name="Test User",
            password_hash="hashed",
            is_active=True,
        )
        test_session.add(user)
        test_session.commit()
        test_session.refresh(user)

        agg = UserAggregatorModel(
            user_id=user.id,
            name="Non-default",
            url="https://example.com",
            is_default=False,
        )
        test_session.add(agg)
        test_session.commit()

        result = service.get_default_aggregator_url(user.id)

        assert result is None

    def test_get_default_url_when_no_aggregators(self, test_session: Session):
        """Test returns None when user has no aggregators."""
        service = UserAggregatorService(test_session)

        # Create user without aggregators
        user = UserModel(
            username="testuser",
            email="test@example.com",
            full_name="Test User",
            password_hash="hashed",
            is_active=True,
        )
        test_session.add(user)
        test_session.commit()
        test_session.refresh(user)

        result = service.get_default_aggregator_url(user.id)

        assert result is None
