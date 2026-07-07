"""Tests for UserAggregatorRepository."""

import pytest
from sqlalchemy.orm import Session

from syfthub.models.user import UserModel
from syfthub.models.user_aggregator import UserAggregatorModel
from syfthub.repositories.user_aggregator import UserAggregatorRepository


@pytest.fixture
def sample_aggregator_data() -> dict:
    """Sample aggregator data for testing."""
    return {
        "name": "Test Aggregator",
        "url": "https://aggregator.example.com",
        "is_default": False,
    }


@pytest.fixture
def test_user(test_session: Session) -> UserModel:
    """Create a test user."""
    user = UserModel(
        username="testuser",
        email="test@example.com",
        full_name="Test User",
        password_hash="hashed_password",
        is_active=True,
    )
    test_session.add(user)
    test_session.commit()
    test_session.refresh(user)
    return user


@pytest.fixture
def test_user2(test_session: Session) -> UserModel:
    """Create a second test user."""
    user = UserModel(
        username="testuser2",
        email="test2@example.com",
        full_name="Test User 2",
        password_hash="hashed_password2",
        is_active=True,
    )
    test_session.add(user)
    test_session.commit()
    test_session.refresh(user)
    return user


class TestUserAggregatorRepositoryGetByUserId:
    """Tests for get_by_user_id method."""

    def test_get_by_user_id_returns_empty_list_when_no_aggregators(
        self, test_session: Session, test_user: UserModel
    ):
        """Test returns empty list when user has no aggregators."""
        repo = UserAggregatorRepository(test_session)
        aggregators = repo.get_by_user_id(test_user.id)
        assert aggregators == []

    def test_get_by_user_id_returns_aggregators_for_user(
        self, test_session: Session, test_user: UserModel, sample_aggregator_data: dict
    ):
        """Test returns all aggregators for a user."""
        repo = UserAggregatorRepository(test_session)

        # Create aggregators for test user
        agg1 = UserAggregatorModel(user_id=test_user.id, **sample_aggregator_data)
        agg2 = UserAggregatorModel(
            user_id=test_user.id,
            name="Second Aggregator",
            url="https://aggregator2.example.com",
            is_default=True,
        )
        test_session.add_all([agg1, agg2])
        test_session.commit()

        aggregators = repo.get_by_user_id(test_user.id)
        assert len(aggregators) == 2
        names = {agg.name for agg in aggregators}
        assert names == {"Test Aggregator", "Second Aggregator"}

    def test_get_by_user_id_returns_only_users_aggregators(
        self,
        test_session: Session,
        test_user: UserModel,
        test_user2: UserModel,
        sample_aggregator_data: dict,
    ):
        """Test returns only aggregators belonging to the specified user."""
        repo = UserAggregatorRepository(test_session)

        # Create aggregators for different users
        agg1 = UserAggregatorModel(user_id=test_user.id, **sample_aggregator_data)
        agg2 = UserAggregatorModel(
            user_id=test_user2.id,
            name="Other User Aggregator",
            url="https://other.example.com",
            is_default=False,
        )
        test_session.add_all([agg1, agg2])
        test_session.commit()

        aggregators = repo.get_by_user_id(test_user.id)
        assert len(aggregators) == 1
        assert aggregators[0].name == "Test Aggregator"

    def test_get_by_user_id_orders_by_created_at_desc(
        self, test_session: Session, test_user: UserModel
    ):
        """Test aggregators are ordered by created_at descending."""
        repo = UserAggregatorRepository(test_session)

        # Create aggregators with different timestamps
        # Note: Only one can have is_default=True due to unique constraint
        agg1 = UserAggregatorModel(
            user_id=test_user.id,
            name="First Aggregator",
            url="https://first.example.com",
            is_default=True,
        )
        test_session.add(agg1)
        test_session.commit()
        test_session.refresh(agg1)

        # Update first to non-default so we can create second as default
        # This is a workaround for the unique constraint
        agg1.is_default = False
        test_session.commit()

        agg2 = UserAggregatorModel(
            user_id=test_user.id,
            name="Second Aggregator",
            url="https://second.example.com",
            is_default=True,
        )
        test_session.add(agg2)
        test_session.commit()

        aggregators = repo.get_by_user_id(test_user.id)
        assert len(aggregators) == 2
        assert aggregators[0].name == "Second Aggregator"
        assert aggregators[1].name == "First Aggregator"


class TestUserAggregatorRepositoryGetDefaultByUserId:
    """Tests for get_default_by_user_id method."""

    def test_get_default_by_user_id_returns_none_when_no_default(
        self, test_session: Session, test_user: UserModel, sample_aggregator_data: dict
    ):
        """Test returns None when no default aggregator exists."""
        repo = UserAggregatorRepository(test_session)

        # Create non-default aggregator
        agg = UserAggregatorModel(user_id=test_user.id, **sample_aggregator_data)
        test_session.add(agg)
        test_session.commit()

        default = repo.get_default_by_user_id(test_user.id)
        assert default is None

    def test_get_default_by_user_id_returns_default_aggregator(
        self, test_session: Session, test_user: UserModel
    ):
        """Test returns the default aggregator."""
        repo = UserAggregatorRepository(test_session)

        # Create default aggregator
        agg = UserAggregatorModel(
            user_id=test_user.id,
            name="Default Aggregator",
            url="https://default.example.com",
            is_default=True,
        )
        test_session.add(agg)
        test_session.commit()
        test_session.refresh(agg)

        default = repo.get_default_by_user_id(test_user.id)
        assert default is not None
        assert default.id == agg.id
        assert default.is_default is True

    def test_get_default_by_user_id_returns_none_for_nonexistent_user(
        self, test_session: Session
    ):
        """Test returns None for non-existent user."""
        repo = UserAggregatorRepository(test_session)
        default = repo.get_default_by_user_id(99999)
        assert default is None


class TestUserAggregatorRepositoryCreate:
    """Tests for create method."""

    def test_create_aggregator_successfully(
        self, test_session: Session, test_user: UserModel, sample_aggregator_data: dict
    ):
        """Test creating an aggregator successfully."""
        repo = UserAggregatorRepository(test_session)

        aggregator = UserAggregatorModel(user_id=test_user.id, **sample_aggregator_data)
        created = repo.create(aggregator)

        assert created is not None
        assert created.id is not None
        assert created.name == sample_aggregator_data["name"]
        assert created.url == sample_aggregator_data["url"]
        assert created.is_default == sample_aggregator_data["is_default"]
        assert created.user_id == test_user.id

    def test_create_aggregator_with_is_default_true(
        self, test_session: Session, test_user: UserModel
    ):
        """Test creating an aggregator with is_default=True."""
        repo = UserAggregatorRepository(test_session)

        aggregator = UserAggregatorModel(
            user_id=test_user.id,
            name="Default Aggregator",
            url="https://default.example.com",
            is_default=True,
        )
        created = repo.create(aggregator)

        assert created is not None
        assert created.is_default is True


class TestUserAggregatorRepositoryUpdate:
    """Tests for update method."""

    def test_update_with_dict(self, test_session: Session, test_user: UserModel):
        """Test updating with a regular dict."""
        repo = UserAggregatorRepository(test_session)

        # Create aggregator
        agg = UserAggregatorModel(
            user_id=test_user.id,
            name="Original Name",
            url="https://original.example.com",
            is_default=False,
        )
        test_session.add(agg)
        test_session.commit()
        test_session.refresh(agg)

        # Update with dict
        updated = repo.update(
            agg.id, {"name": "Updated Name", "url": "https://updated.example.com"}
        )

        assert updated is not None
        assert updated.name == "Updated Name"
        assert updated.url == "https://updated.example.com"
        assert updated.is_default is False  # Unchanged

    def test_update_with_pydantic_v2_model(
        self, test_session: Session, test_user: UserModel
    ):
        """Test updating with a Pydantic v2 model (model_dump)."""
        from syfthub.schemas.user import UserAggregatorUpdate

        repo = UserAggregatorRepository(test_session)

        # Create aggregator
        agg = UserAggregatorModel(
            user_id=test_user.id,
            name="Original Name",
            url="https://original.example.com",
            is_default=False,
        )
        test_session.add(agg)
        test_session.commit()
        test_session.refresh(agg)

        # Update with Pydantic model
        update_data = UserAggregatorUpdate(name="Pydantic Updated", is_default=True)
        updated = repo.update(agg.id, update_data)

        assert updated is not None
        assert updated.name == "Pydantic Updated"
        assert updated.is_default is True
        assert updated.url == "https://original.example.com"  # Unchanged

    def test_update_returns_none_for_nonexistent_aggregator(
        self, test_session: Session
    ):
        """Test update returns None for non-existent aggregator."""
        repo = UserAggregatorRepository(test_session)
        updated = repo.update(99999, {"name": "New Name"})
        assert updated is None

    def test_update_partial_fields(self, test_session: Session, test_user: UserModel):
        """Test updating only some fields."""
        repo = UserAggregatorRepository(test_session)

        # Create aggregator
        agg = UserAggregatorModel(
            user_id=test_user.id,
            name="Original Name",
            url="https://original.example.com",
            is_default=False,
        )
        test_session.add(agg)
        test_session.commit()
        test_session.refresh(agg)

        # Update only name
        updated = repo.update(agg.id, {"name": "Only Name Updated"})

        assert updated is not None
        assert updated.name == "Only Name Updated"
        assert updated.url == "https://original.example.com"  # Unchanged
        assert updated.is_default is False  # Unchanged


class TestUserAggregatorRepositoryDelete:
    """Tests for delete method (inherited from BaseRepository)."""

    def test_delete_existing_aggregator(
        self, test_session: Session, test_user: UserModel
    ):
        """Test deleting an existing aggregator."""
        repo = UserAggregatorRepository(test_session)

        # Create aggregator
        agg = UserAggregatorModel(
            user_id=test_user.id,
            name="To Delete",
            url="https://delete.example.com",
            is_default=False,
        )
        test_session.add(agg)
        test_session.commit()
        test_session.refresh(agg)

        # Delete
        success = repo.delete(agg.id)
        assert success is True

        # Verify deleted
        deleted = repo.get_by_id(agg.id)
        assert deleted is None

    def test_delete_returns_false_for_nonexistent_aggregator(
        self, test_session: Session
    ):
        """Test delete returns False for non-existent aggregator."""
        repo = UserAggregatorRepository(test_session)
        success = repo.delete(99999)
        assert success is False
