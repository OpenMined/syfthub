"""User aggregators resource for SyftHub SDK."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from syfthub_sdk.models import UserAggregator

if TYPE_CHECKING:
    from syfthub_sdk._http import HTTPClient


class AggregatorsResource:
    """Manage user's aggregator configurations.

    Aggregators are custom RAG orchestration service endpoints that users can
    configure to use for chat operations. Each user can have multiple aggregator
    configurations, with one set as the default.

    The first aggregator created is automatically set as the default. Only one
    aggregator can be the default at a time; setting a new default automatically
    unsets the previous one.

    Example usage:
        # List all aggregators
        aggregators = client.users.aggregators.list()
        for agg in aggregators:
            print(f"{agg.name}: {agg.url}")

        # Create a new aggregator
        agg = client.users.aggregators.create(
            name="My Custom Aggregator",
            url="https://my-aggregator.example.com"
        )

        # Update an aggregator
        agg = client.users.aggregators.update(
            aggregator_id=1,
            name="Updated Name",
            url="https://new-url.example.com"
        )

        # Set as default
        agg = client.users.aggregators.set_default(aggregator_id=1)

        # Delete an aggregator
        client.users.aggregators.delete(aggregator_id=1)
    """

    def __init__(self, http: HTTPClient) -> None:
        """Initialize aggregators resource.

        Args:
            http: HTTP client instance
        """
        self._http = http

    def list(self) -> list[UserAggregator]:
        """List all aggregator configurations for the current user.

        Returns:
            List of UserAggregator objects

        Raises:
            AuthenticationError: If not authenticated

        Example:
            aggregators = client.users.aggregators.list()
            for agg in aggregators:
                if agg.is_default:
                    print(f"Default: {agg.name}")
        """
        response = self._http.get("/api/v1/users/me/aggregators")
        items = response if isinstance(response, list) else []
        return [UserAggregator.model_validate(item) for item in items]

    def get(self, aggregator_id: int) -> UserAggregator:
        """Get a specific aggregator configuration by ID.

        Args:
            aggregator_id: The aggregator ID

        Returns:
            The UserAggregator object

        Raises:
            AuthenticationError: If not authenticated
            NotFoundError: If aggregator not found

        Example:
            agg = client.users.aggregators.get(1)
            print(f"{agg.name}: {agg.url}")
        """
        response = self._http.get(f"/api/v1/users/me/aggregators/{aggregator_id}")
        data = response if isinstance(response, dict) else {}
        return UserAggregator.model_validate(data)

    def create(
        self,
        *,
        name: str,
        url: str,
    ) -> UserAggregator:
        """Create a new aggregator configuration.

        The first aggregator created is automatically set as the default.

        Args:
            name: Display name for the aggregator
            url: Aggregator service URL

        Returns:
            The created UserAggregator object

        Raises:
            AuthenticationError: If not authenticated
            ValidationError: If input is invalid

        Example:
            agg = client.users.aggregators.create(
                name="My Custom Aggregator",
                url="https://my-aggregator.example.com"
            )
            print(f"Created: {agg.id}")
        """
        payload: dict[str, Any] = {
            "name": name,
            "url": url,
        }
        response = self._http.post("/api/v1/users/me/aggregators", json=payload)
        data = response if isinstance(response, dict) else {}
        return UserAggregator.model_validate(data)

    def update(
        self,
        aggregator_id: int,
        *,
        name: str | None = None,
        url: str | None = None,
    ) -> UserAggregator:
        """Update an aggregator configuration.

        Only provided fields will be updated.

        Args:
            aggregator_id: The aggregator ID to update
            name: New display name (optional)
            url: New aggregator URL (optional)

        Returns:
            The updated UserAggregator object

        Raises:
            AuthenticationError: If not authenticated
            NotFoundError: If aggregator not found
            ValidationError: If input is invalid

        Example:
            agg = client.users.aggregators.update(
                aggregator_id=1,
                name="Updated Name"
            )
        """
        payload: dict[str, Any] = {}
        if name is not None:
            payload["name"] = name
        if url is not None:
            payload["url"] = url

        response = self._http.put(
            f"/api/v1/users/me/aggregators/{aggregator_id}",
            json=payload,
        )
        data = response if isinstance(response, dict) else {}
        return UserAggregator.model_validate(data)

    def delete(self, aggregator_id: int) -> None:
        """Delete an aggregator configuration.

        Args:
            aggregator_id: The aggregator ID to delete

        Raises:
            AuthenticationError: If not authenticated
            NotFoundError: If aggregator not found

        Example:
            client.users.aggregators.delete(1)
        """
        self._http.delete(f"/api/v1/users/me/aggregators/{aggregator_id}")

    def set_default(self, aggregator_id: int) -> UserAggregator:
        """Set an aggregator as the default.

        Only one aggregator can be the default at a time. Setting a new default
        automatically unsets the previous one.

        Args:
            aggregator_id: The aggregator ID to set as default

        Returns:
            The updated UserAggregator object with is_default=True

        Raises:
            AuthenticationError: If not authenticated
            NotFoundError: If aggregator not found

        Example:
            agg = client.users.aggregators.set_default(2)
            print(f"{agg.name} is now the default")
        """
        response = self._http.patch(
            f"/api/v1/users/me/aggregators/{aggregator_id}/default"
        )
        data = response if isinstance(response, dict) else {}
        return UserAggregator.model_validate(data)
