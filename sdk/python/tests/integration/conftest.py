"""Pytest fixtures for integration tests."""

from __future__ import annotations

import contextlib
import os
import uuid
from collections.abc import Generator

import httpx
import pytest

from syfthub_sdk import EndpointType, SyftHubClient
from syfthub_sdk.exceptions import SyftHubError


def get_backend_url() -> str:
    """Get backend URL from environment or default."""
    return os.environ.get("SYFTHUB_TEST_URL", "http://localhost:8000")


def is_backend_available() -> bool:
    """Check if the backend is available."""
    try:
        url = get_backend_url()
        response = httpx.get(f"{url}/health", timeout=5.0)
        return response.status_code == 200
    except Exception:
        return False


# Skip all integration tests if backend not available
pytestmark = pytest.mark.skipif(
    not is_backend_available(),
    reason=f"Backend not available at {get_backend_url()}",
)


@pytest.fixture(scope="session")
def backend_url() -> str:
    """Return the backend URL for tests."""
    return get_backend_url()


@pytest.fixture
def client(backend_url: str) -> Generator[SyftHubClient, None, None]:
    """Create a fresh SyftHubClient for each test."""
    with SyftHubClient(base_url=backend_url) as c:
        yield c


@pytest.fixture
def unique_id() -> str:
    """Generate a unique ID for test data."""
    return uuid.uuid4().hex[:8]


@pytest.fixture
def test_user_credentials(unique_id: str) -> dict[str, str]:
    """Generate unique credentials for a test user."""
    return {
        "username": f"testuser_{unique_id}",
        "email": f"test_{unique_id}@example.com",
        "password": "TestPass123!",
        "full_name": f"Test User {unique_id}",
    }


@pytest.fixture
def registered_user(
    client: SyftHubClient,
    test_user_credentials: dict[str, str],
) -> Generator[dict[str, str], None, None]:
    """Register a test user and return credentials.

    Cleans up by attempting to delete the user after the test.
    Note: Deletion may fail if backend doesn't support it or user lacks permission.
    """
    # Register the user
    client.auth.register(
        username=test_user_credentials["username"],
        email=test_user_credentials["email"],
        password=test_user_credentials["password"],
        full_name=test_user_credentials["full_name"],
    )

    yield test_user_credentials

    # Cleanup: Try to delete the user (best effort)
    # Login as the user and attempt cleanup
    # Note: User deletion endpoint may require admin rights
    with contextlib.suppress(SyftHubError):
        client.auth.login(
            username=test_user_credentials["username"],
            password=test_user_credentials["password"],
        )


@pytest.fixture
def authenticated_client(
    backend_url: str,
    registered_user: dict[str, str],
) -> Generator[SyftHubClient, None, None]:
    """Create a client that's logged in as a test user."""
    with SyftHubClient(base_url=backend_url) as c:
        c.auth.login(
            username=registered_user["username"],
            password=registered_user["password"],
        )
        yield c


@pytest.fixture
def second_user_credentials(unique_id: str) -> dict[str, str]:
    """Generate credentials for a second test user."""
    return {
        "username": f"testuser2_{unique_id}",
        "email": f"test2_{unique_id}@example.com",
        "password": "TestPass456!",
        "full_name": f"Test User 2 {unique_id}",
    }


@pytest.fixture
def second_authenticated_client(
    backend_url: str,
    client: SyftHubClient,
    second_user_credentials: dict[str, str],
) -> Generator[SyftHubClient, None, None]:
    """Create a second authenticated client (different user)."""
    # Register second user
    client.auth.register(
        username=second_user_credentials["username"],
        email=second_user_credentials["email"],
        password=second_user_credentials["password"],
        full_name=second_user_credentials["full_name"],
    )

    # Create new client and login
    with SyftHubClient(base_url=backend_url) as c:
        c.auth.login(
            username=second_user_credentials["username"],
            password=second_user_credentials["password"],
        )
        yield c


@pytest.fixture
def created_endpoint(
    authenticated_client: SyftHubClient,
    registered_user: dict[str, str],
    unique_id: str,
) -> Generator[dict[str, object], None, None]:
    """Create a test endpoint and clean up after.

    Returns dict with endpoint data, client, username, and path for cleanup.
    """
    username = registered_user["username"]
    endpoint = authenticated_client.my_endpoints.create(
        name=f"Test Endpoint {unique_id}",
        type=EndpointType.MODEL,
        visibility="public",
        description="A test endpoint for integration tests",
        version="1.0.0",
        readme=f"# Test Endpoint\n\nCreated for test {unique_id}",
    )

    path = f"{username}/{endpoint.slug}"

    yield {
        "endpoint": endpoint,
        "client": authenticated_client,
        "unique_id": unique_id,
        "username": username,
        "path": path,
    }

    # Cleanup: delete the endpoint
    with contextlib.suppress(SyftHubError):
        authenticated_client.my_endpoints.delete(path)
