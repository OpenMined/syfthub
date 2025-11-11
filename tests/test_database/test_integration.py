"""Integration tests for complete database workflows."""

from decimal import Decimal

from sqlalchemy.orm import Session

from syfthub.database.repositories import (
    DatasiteRepository,
    ItemRepository,
    UserRepository,
)
from syfthub.schemas.auth import UserRole
from syfthub.schemas.datasite import DatasiteVisibility


class TestCompleteWorkflows:
    """Tests for complete database workflows."""

    def test_user_item_datasite_workflow(self, test_session: Session):
        """Test complete workflow: create user, add items and datasites, verify relationships."""
        # Create repositories
        user_repo = UserRepository(test_session)
        item_repo = ItemRepository(test_session)
        datasite_repo = DatasiteRepository(test_session)

        # 1. Create user
        user_data = {
            "username": "workflowuser",
            "email": "workflow@example.com",
            "full_name": "Workflow User",
            "age": 30,
            "role": UserRole.USER.value,
            "password_hash": "hashed_password",
            "is_active": True,
        }
        user = user_repo.create(user_data)
        assert user.id is not None

        # 2. Create multiple items for the user
        item_names = ["Laptop", "Mouse", "Keyboard"]
        created_items = []

        for name in item_names:
            item_data = {
                "user_id": user.id,
                "name": name,
                "description": f"A {name.lower()} for work",
                "price": Decimal("100.00"),
                "is_available": True,
                "category": "electronics",
            }
            item = item_repo.create(item_data)
            created_items.append(item)

        # 3. Create multiple datasites for the user
        datasite_configs = [
            {
                "name": "Public Project",
                "slug": "public-project",
                "visibility": DatasiteVisibility.PUBLIC,
            },
            {
                "name": "Private Project",
                "slug": "private-project",
                "visibility": DatasiteVisibility.PRIVATE,
            },
            {
                "name": "Internal Tool",
                "slug": "internal-tool",
                "visibility": DatasiteVisibility.INTERNAL,
            },
        ]
        created_datasites = []

        for config in datasite_configs:
            datasite_data = {
                "user_id": user.id,
                "name": config["name"],
                "slug": config["slug"],
                "description": f"Description for {config['name']}",
                "visibility": config["visibility"].value,
                "is_active": True,
            }
            datasite = datasite_repo.create(datasite_data)
            created_datasites.append(datasite)

        # 4. Verify user's items
        user_items = item_repo.get_by_user_id(user.id)
        assert len(user_items) == 3
        item_names_retrieved = [item.name for item in user_items]
        assert set(item_names_retrieved) == set(item_names)

        # 5. Verify user's datasites
        user_datasites = datasite_repo.get_by_user_id(user.id)
        assert len(user_datasites) == 3

        # 6. Verify public datasites only
        public_datasites = datasite_repo.get_public_by_user_id(user.id)
        assert len(public_datasites) == 1
        assert public_datasites[0].name == "Public Project"
        assert public_datasites[0].visibility == DatasiteVisibility.PUBLIC

        # 7. Test slug uniqueness per user
        assert datasite_repo.slug_exists_for_user(user.id, "public-project") is True
        assert datasite_repo.slug_exists_for_user(user.id, "nonexistent-slug") is False

        # 8. Update user and verify changes propagate
        updated_user = user_repo.update(user.id, {"full_name": "Updated Workflow User"})
        assert updated_user.full_name == "Updated Workflow User"

        # 9. Update item and verify
        first_item = created_items[0]
        updated_item = item_repo.update(first_item.id, {"price": Decimal("150.00")})
        assert updated_item.price == Decimal("150.00")

        # 10. Update datasite visibility and verify
        first_datasite = created_datasites[0]
        updated_datasite = datasite_repo.update(
            first_datasite.id, {"visibility": DatasiteVisibility.PRIVATE.value}
        )
        assert updated_datasite.visibility == DatasiteVisibility.PRIVATE

        # Verify public datasites list is now empty
        public_datasites_after_update = datasite_repo.get_public_by_user_id(user.id)
        assert len(public_datasites_after_update) == 0

    def test_multi_user_data_isolation(self, test_session: Session):
        """Test that data is properly isolated between users."""
        # Create repositories
        user_repo = UserRepository(test_session)
        item_repo = ItemRepository(test_session)
        datasite_repo = DatasiteRepository(test_session)

        # Create two users
        user1_data = {
            "username": "user1",
            "email": "user1@example.com",
            "full_name": "User One",
            "role": UserRole.USER.value,
            "password_hash": "hash1",
            "is_active": True,
        }
        user2_data = {
            "username": "user2",
            "email": "user2@example.com",
            "full_name": "User Two",
            "role": UserRole.USER.value,
            "password_hash": "hash2",
            "is_active": True,
        }

        user1 = user_repo.create(user1_data)
        user2 = user_repo.create(user2_data)

        # Create items for each user
        item1_data = {
            "user_id": user1.id,
            "name": "User1 Item",
            "description": "Item for user 1",
            "price": Decimal("50.00"),
            "is_available": True,
        }
        item2_data = {
            "user_id": user2.id,
            "name": "User2 Item",
            "description": "Item for user 2",
            "price": Decimal("75.00"),
            "is_available": True,
        }

        item_repo.create(item1_data)
        item_repo.create(item2_data)

        # Create datasites with same slug for each user
        datasite1_data = {
            "user_id": user1.id,
            "name": "Shared Name Project",
            "slug": "shared-slug",
            "description": "User 1's project",
            "visibility": DatasiteVisibility.PUBLIC.value,
            "is_active": True,
        }
        datasite2_data = {
            "user_id": user2.id,
            "name": "Shared Name Project",
            "slug": "shared-slug",  # Same slug, different user
            "description": "User 2's project",
            "visibility": DatasiteVisibility.PUBLIC.value,
            "is_active": True,
        }

        datasite_repo.create(datasite1_data)
        datasite_repo.create(datasite2_data)

        # Verify data isolation

        # User 1's items
        user1_items = item_repo.get_by_user_id(user1.id)
        assert len(user1_items) == 1
        assert user1_items[0].name == "User1 Item"

        # User 2's items
        user2_items = item_repo.get_by_user_id(user2.id)
        assert len(user2_items) == 1
        assert user2_items[0].name == "User2 Item"

        # User 1's datasites
        user1_datasites = datasite_repo.get_by_user_id(user1.id)
        assert len(user1_datasites) == 1
        assert user1_datasites[0].description == "User 1's project"

        # User 2's datasites
        user2_datasites = datasite_repo.get_by_user_id(user2.id)
        assert len(user2_datasites) == 1
        assert user2_datasites[0].description == "User 2's project"

        # Verify slug uniqueness per user (not global)
        user1_datasite = datasite_repo.get_by_user_and_slug(user1.id, "shared-slug")
        user2_datasite = datasite_repo.get_by_user_and_slug(user2.id, "shared-slug")

        assert user1_datasite is not None
        assert user2_datasite is not None
        assert user1_datasite.id != user2_datasite.id
        assert user1_datasite.description == "User 1's project"
        assert user2_datasite.description == "User 2's project"

    def test_user_deletion_cascade(self, test_session: Session):
        """Test that deleting a user properly handles related data."""
        # Create repositories
        user_repo = UserRepository(test_session)
        item_repo = ItemRepository(test_session)
        datasite_repo = DatasiteRepository(test_session)

        # Create user
        user_data = {
            "username": "deleteuser",
            "email": "delete@example.com",
            "full_name": "Delete User",
            "role": UserRole.USER.value,
            "password_hash": "hash",
            "is_active": True,
        }
        user = user_repo.create(user_data)

        # Create item for user
        item_data = {
            "user_id": user.id,
            "name": "Test Item",
            "description": "Test item",
            "price": Decimal("25.00"),
            "is_available": True,
        }
        item = item_repo.create(item_data)

        # Create datasite for user
        datasite_data = {
            "user_id": user.id,
            "name": "Test Datasite",
            "slug": "test-datasite",
            "description": "Test datasite",
            "visibility": DatasiteVisibility.PUBLIC.value,
            "is_active": True,
        }
        datasite = datasite_repo.create(datasite_data)

        # Verify data exists
        assert user_repo.get_by_id(user.id) is not None
        assert item_repo.get_by_id(item.id) is not None
        assert datasite_repo.get_by_id(datasite.id) is not None

        # Delete user
        result = user_repo.delete(user.id)
        assert result is True

        # Verify user is deleted
        assert user_repo.get_by_id(user.id) is None

        # Verify related data is also deleted (due to cascade)
        assert item_repo.get_by_id(item.id) is None
        assert datasite_repo.get_by_id(datasite.id) is None

    def test_pagination_and_ordering(self, test_session: Session):
        """Test pagination and ordering functionality."""
        # Create repositories
        user_repo = UserRepository(test_session)
        item_repo = ItemRepository(test_session)

        # Create user
        user_data = {
            "username": "paginationuser",
            "email": "pagination@example.com",
            "full_name": "Pagination User",
            "role": UserRole.USER.value,
            "password_hash": "hash",
            "is_active": True,
        }
        user = user_repo.create(user_data)

        # Create multiple items with different timestamps
        item_names = [f"Item {i:02d}" for i in range(10)]

        for name in item_names:
            item_data = {
                "user_id": user.id,
                "name": name,
                "description": f"Description for {name}",
                "price": Decimal("10.00"),
                "is_available": True,
            }
            item_repo.create(item_data)

        # Test pagination
        page1 = item_repo.get_by_user_id(user.id, skip=0, limit=3)
        page2 = item_repo.get_by_user_id(user.id, skip=3, limit=3)
        page3 = item_repo.get_by_user_id(user.id, skip=6, limit=3)
        page4 = item_repo.get_by_user_id(user.id, skip=9, limit=3)

        assert len(page1) == 3
        assert len(page2) == 3
        assert len(page3) == 3
        assert len(page4) == 1  # Only one item left

        # Verify no overlap between pages
        all_items_paginated = page1 + page2 + page3 + page4
        item_ids = [item.id for item in all_items_paginated]
        assert len(set(item_ids)) == 10  # All unique IDs

        # Test global pagination
        all_items_page1 = item_repo.get_all(skip=0, limit=5)
        all_items_page2 = item_repo.get_all(skip=5, limit=5)

        assert len(all_items_page1) == 5
        assert len(all_items_page2) == 5
