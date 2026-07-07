"""Additional tests for UserAggregatorService missing branches."""

from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from syfthub.services.user_aggregator_service import UserAggregatorService


@pytest.fixture
def service():
    session = MagicMock()
    svc = UserAggregatorService(session)
    svc.aggregator_repository = MagicMock()
    return svc


class TestUpdateAggregatorMissingBranches:
    def test_raises_500_when_update_returns_none(self, service):
        mock_agg = MagicMock()
        mock_agg.id = 1
        mock_agg.user_id = 10
        mock_agg.is_default = False
        service.aggregator_repository.get_by_id.return_value = mock_agg
        service.aggregator_repository.update.return_value = None

        from syfthub.schemas.user import UserAggregatorUpdate

        with pytest.raises(HTTPException) as exc_info:
            service.update_aggregator(1, 10, UserAggregatorUpdate(name="new"))
        assert exc_info.value.status_code == 500

    def test_existing_default_unset_when_setting_new_default(self, service):
        mock_agg = MagicMock()
        mock_agg.id = 1
        mock_agg.user_id = 10
        mock_agg.is_default = False

        other_default = MagicMock()
        other_default.id = 2
        other_default.is_default = True

        service.aggregator_repository.get_by_id.return_value = mock_agg
        service.aggregator_repository.get_by_user_id.return_value = [
            mock_agg,
            other_default,
        ]
        mock_updated = MagicMock()
        service.aggregator_repository.update.return_value = mock_updated
        mock_updated.id = 1
        mock_updated.user_id = 10
        mock_updated.name = "updated"
        mock_updated.url = "http://localhost"
        mock_updated.is_default = True
        mock_updated.created_at = None
        mock_updated.updated_at = None

        from unittest.mock import patch

        from syfthub.schemas.user import UserAggregatorUpdate

        with patch(
            "syfthub.schemas.user.UserAggregatorResponse.model_validate"
        ) as mock_validate:
            mock_validate.return_value = MagicMock()
            service.update_aggregator(1, 10, UserAggregatorUpdate(is_default=True))

        service.aggregator_repository.update.assert_called()


class TestDeleteAggregatorMissingBranches:
    def test_raises_500_when_delete_fails(self, service):
        mock_agg = MagicMock()
        mock_agg.id = 1
        mock_agg.user_id = 10
        mock_agg.is_default = False
        service.aggregator_repository.get_by_id.return_value = mock_agg
        service.aggregator_repository.delete.return_value = False

        with pytest.raises(HTTPException) as exc_info:
            service.delete_aggregator(1, 10)
        assert exc_info.value.status_code == 500

    def test_sets_new_default_after_deleting_default(self, service):
        mock_agg = MagicMock()
        mock_agg.id = 1
        mock_agg.user_id = 10
        mock_agg.is_default = True

        remaining = MagicMock()
        remaining.id = 2
        remaining.is_default = False

        service.aggregator_repository.get_by_id.return_value = mock_agg
        service.aggregator_repository.delete.return_value = True
        service.aggregator_repository.get_by_user_id.return_value = [remaining]
        service.aggregator_repository.update.return_value = remaining

        service.delete_aggregator(1, 10)
        service.aggregator_repository.update.assert_called()


class TestSetDefaultAggregatorMissingBranches:
    def test_raises_500_when_update_returns_none(self, service):
        mock_agg = MagicMock()
        mock_agg.id = 1
        mock_agg.user_id = 10
        mock_agg.is_default = False

        service.aggregator_repository.get_by_id.return_value = mock_agg
        service.aggregator_repository.get_by_user_id.return_value = [mock_agg]
        service.aggregator_repository.update.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            service.set_default_aggregator(1, 10)
        assert exc_info.value.status_code == 500
