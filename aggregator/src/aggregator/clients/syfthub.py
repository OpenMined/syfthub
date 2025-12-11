"""SyftHub client for resolving endpoint details."""

import logging
from typing import Any

import httpx

from aggregator.core.config import Settings
from aggregator.schemas.internal import ResolvedEndpoint

logger = logging.getLogger(__name__)


class SyftHubClientError(Exception):
    """Error communicating with SyftHub."""

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class EndpointNotFoundError(SyftHubClientError):
    """Endpoint not found in SyftHub."""

    pass


class EndpointAccessDeniedError(SyftHubClientError):
    """User does not have access to the endpoint."""

    pass


class SyftHubClient:
    """Client for interacting with SyftHub to resolve endpoint details."""

    def __init__(self, settings: Settings):
        self.base_url = settings.syfthub_url.rstrip("/")
        self.timeout = httpx.Timeout(10.0)

    async def resolve_endpoint(
        self,
        path: str,
        user_token: str | None = None,
    ) -> ResolvedEndpoint:
        """
        Resolve an endpoint path to its connection details.

        Args:
            path: Endpoint path in format "owner/slug"
            user_token: Optional user token for accessing private endpoints

        Returns:
            ResolvedEndpoint with URL and metadata

        Raises:
            EndpointNotFoundError: If endpoint doesn't exist
            EndpointAccessDeniedError: If user can't access the endpoint
            SyftHubClientError: For other errors
        """
        # Validate path format
        if "/" not in path:
            raise SyftHubClientError(f"Invalid endpoint path format: {path}")

        headers: dict[str, str] = {"Accept": "application/json"}
        if user_token:
            headers["Authorization"] = f"Bearer {user_token}"

        url = f"{self.base_url}/{path}"

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.get(url, headers=headers)

                if response.status_code == 404:
                    raise EndpointNotFoundError(
                        f"Endpoint not found: {path}",
                        status_code=404,
                    )

                if response.status_code in (401, 403):
                    raise EndpointAccessDeniedError(
                        f"Access denied to endpoint: {path}",
                        status_code=response.status_code,
                    )

                response.raise_for_status()
                data = response.json()

                return self._parse_endpoint_response(path, data)

            except httpx.TimeoutException as e:
                raise SyftHubClientError(f"Timeout resolving endpoint: {path}") from e
            except httpx.HTTPStatusError as e:
                raise SyftHubClientError(
                    f"HTTP error resolving endpoint: {e.response.status_code}",
                    status_code=e.response.status_code,
                ) from e
            except httpx.RequestError as e:
                raise SyftHubClientError(f"Network error resolving endpoint: {path}") from e

    def _parse_endpoint_response(self, path: str, data: dict[str, Any]) -> ResolvedEndpoint:
        """Parse SyftHub endpoint response to extract connection URL."""
        # Extract endpoint type
        endpoint_type = data.get("type", "model")
        if endpoint_type not in ("model", "data_source"):
            logger.warning(f"Unknown endpoint type '{endpoint_type}', defaulting to 'model'")
            endpoint_type = "model"

        # Extract URL from connections config
        connections = data.get("connect", []) or data.get("connections", [])
        url = self._extract_url_from_connections(connections, path)

        return ResolvedEndpoint(
            path=path,
            url=url,
            endpoint_type=endpoint_type,  # type: ignore[arg-type]
            name=data.get("name", path),
        )

    def _extract_url_from_connections(
        self,
        connections: list[dict[str, Any]],
        path: str,
    ) -> str:
        """Extract the URL from endpoint connections config."""
        if not connections:
            raise SyftHubClientError(f"Endpoint has no connections configured: {path}")

        # Find the first enabled connection with a URL
        for conn in connections:
            if not conn.get("enabled", True):
                continue

            config = conn.get("config", {})
            url = config.get("url")

            if url:
                return url

        # If no enabled connection with URL found, try the first one
        first_config = connections[0].get("config", {})
        url = first_config.get("url")

        if not url:
            raise SyftHubClientError(f"No URL found in endpoint connections: {path}")

        return url

    async def health_check(self) -> bool:
        """Check if SyftHub is reachable."""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.get(f"{self.base_url}/health")
                return response.status_code == 200
            except httpx.RequestError:
                return False
