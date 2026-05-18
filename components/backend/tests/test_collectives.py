"""Tests for the Collectives feature (collectives + membership workflow)."""

import pytest
from fastapi.testclient import TestClient

from syfthub.auth.security import token_blacklist
from syfthub.main import app

API = "/api/v1"


@pytest.fixture
def client() -> TestClient:
    """Create a test client with a clean database."""
    from syfthub.database.connection import create_tables, drop_tables

    drop_tables()
    create_tables()
    yield TestClient(app)
    drop_tables()


@pytest.fixture(autouse=True)
def reset_auth_data() -> None:
    """Reset authentication state before each test."""
    token_blacklist.clear()
    yield


def _register_and_login(client: TestClient, username: str) -> dict:
    """Register a user and return Authorization headers."""
    user_data = {
        "username": username,
        "email": f"{username}@example.com",
        "full_name": f"{username.title()} User",
        "password": "testpassword123",
    }
    resp = client.post(f"{API}/auth/register", json=user_data)
    assert resp.status_code == 201, resp.text
    resp = client.post(
        f"{API}/auth/login",
        data={"username": username, "password": "testpassword123"},
    )
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


@pytest.fixture
def owner_headers(client: TestClient) -> dict:
    """Headers for the collective owner."""
    return _register_and_login(client, "owner")


@pytest.fixture
def member_headers(client: TestClient) -> dict:
    """Headers for a separate user who owns endpoints."""
    return _register_and_login(client, "member")


def _create_endpoint(
    client: TestClient, headers: dict, name: str, visibility: str = "public"
) -> int:
    """Create an endpoint and return its ID."""
    resp = client.post(
        f"{API}/endpoints",
        json={"name": name, "type": "model", "visibility": visibility},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _create_collective(
    client: TestClient, headers: dict, name: str = "ML Models", **extra
) -> dict:
    """Create a collective and return the response body."""
    payload = {"name": name, **extra}
    resp = client.post(f"{API}/collectives", json=payload, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()


# ----------------------------------------------------------------------
# Collective CRUD
# ----------------------------------------------------------------------


def test_create_collective(client: TestClient, owner_headers: dict) -> None:
    """A collective is created with a derived slug and zero members."""
    body = _create_collective(
        client,
        owner_headers,
        name="ML Models",
        description="Curated models",
        tags=["nlp", "vision"],
    )
    assert body["slug"] == "ml-models"
    assert body["description"] == "Curated models"
    assert body["auto_approve"] is False
    assert body["member_count"] == 0
    assert sorted(body["tags"]) == ["nlp", "vision"]


def test_create_collective_requires_auth(client: TestClient) -> None:
    """Creating a collective without auth is rejected."""
    resp = client.post(f"{API}/collectives", json={"name": "Anon"})
    assert resp.status_code in (401, 403)


def test_duplicate_slug_rejected(client: TestClient, owner_headers: dict) -> None:
    """An explicit slug that already exists yields 409."""
    _create_collective(client, owner_headers, name="First", slug="shared")
    resp = client.post(
        f"{API}/collectives",
        json={"name": "Second", "slug": "shared"},
        headers=owner_headers,
    )
    assert resp.status_code == 409


def test_derived_slug_collision_gets_suffix(
    client: TestClient, owner_headers: dict
) -> None:
    """A second collective with the same name gets a distinct slug."""
    first = _create_collective(client, owner_headers, name="Vision")
    second = _create_collective(client, owner_headers, name="Vision")
    assert first["slug"] == "vision"
    assert second["slug"] != first["slug"]


def test_get_and_list_and_by_slug(client: TestClient, owner_headers: dict) -> None:
    """A collective is publicly retrievable by ID, slug, and in the list."""
    created = _create_collective(client, owner_headers, name="Data Sets")

    by_id = client.get(f"{API}/collectives/{created['id']}")
    assert by_id.status_code == 200
    assert by_id.json()["id"] == created["id"]

    by_slug = client.get(f"{API}/collectives/by-slug/{created['slug']}")
    assert by_slug.status_code == 200
    assert by_slug.json()["id"] == created["id"]

    listing = client.get(f"{API}/collectives")
    assert listing.status_code == 200
    assert created["id"] in [c["id"] for c in listing.json()]


def test_get_missing_collective_404(client: TestClient) -> None:
    """An unknown collective ID yields 404."""
    assert client.get(f"{API}/collectives/99999").status_code == 404


def test_update_collective_owner_only(
    client: TestClient, owner_headers: dict, member_headers: dict
) -> None:
    """Only the owner can update a collective."""
    collective = _create_collective(client, owner_headers)

    forbidden = client.patch(
        f"{API}/collectives/{collective['id']}",
        json={"description": "hijacked"},
        headers=member_headers,
    )
    assert forbidden.status_code == 403

    ok = client.patch(
        f"{API}/collectives/{collective['id']}",
        json={"description": "updated", "auto_approve": True},
        headers=owner_headers,
    )
    assert ok.status_code == 200
    assert ok.json()["description"] == "updated"
    assert ok.json()["auto_approve"] is True


def test_delete_collective_owner_only(
    client: TestClient, owner_headers: dict, member_headers: dict
) -> None:
    """Only the owner can delete a collective."""
    collective = _create_collective(client, owner_headers)

    assert (
        client.delete(
            f"{API}/collectives/{collective['id']}", headers=member_headers
        ).status_code
        == 403
    )
    assert (
        client.delete(
            f"{API}/collectives/{collective['id']}", headers=owner_headers
        ).status_code
        == 204
    )
    assert client.get(f"{API}/collectives/{collective['id']}").status_code == 404


# ----------------------------------------------------------------------
# Membership — join requests
# ----------------------------------------------------------------------


def test_request_join_pending_when_triaged(
    client: TestClient, owner_headers: dict, member_headers: dict
) -> None:
    """With auto_approve off, a join request lands as pending."""
    collective = _create_collective(client, owner_headers, auto_approve=False)
    endpoint_id = _create_endpoint(client, member_headers, "my-model")

    resp = client.post(
        f"{API}/collectives/{collective['id']}/members",
        json={"endpoint_id": endpoint_id},
        headers=member_headers,
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["status"] == "pending"


def test_request_join_auto_approved(
    client: TestClient, owner_headers: dict, member_headers: dict
) -> None:
    """With auto_approve on, a join request is approved immediately."""
    collective = _create_collective(client, owner_headers, auto_approve=True)
    endpoint_id = _create_endpoint(client, member_headers, "my-model")

    resp = client.post(
        f"{API}/collectives/{collective['id']}/members",
        json={"endpoint_id": endpoint_id},
        headers=member_headers,
    )
    assert resp.status_code == 201
    assert resp.json()["status"] == "approved"

    detail = client.get(f"{API}/collectives/{collective['id']}")
    assert detail.json()["member_count"] == 1


def test_cannot_request_join_with_others_endpoint(
    client: TestClient, owner_headers: dict, member_headers: dict
) -> None:
    """A user cannot enroll an endpoint they do not own."""
    collective = _create_collective(client, owner_headers, auto_approve=True)
    endpoint_id = _create_endpoint(client, member_headers, "members-model")

    resp = client.post(
        f"{API}/collectives/{collective['id']}/members",
        json={"endpoint_id": endpoint_id},
        headers=owner_headers,
    )
    assert resp.status_code == 403


def test_review_request_approve_and_reject(
    client: TestClient, owner_headers: dict, member_headers: dict
) -> None:
    """The collective owner can approve or reject a pending request."""
    collective = _create_collective(client, owner_headers, auto_approve=False)
    cid = collective["id"]
    ep_approve = _create_endpoint(client, member_headers, "approve-me")
    ep_reject = _create_endpoint(client, member_headers, "reject-me")

    for endpoint_id in (ep_approve, ep_reject):
        client.post(
            f"{API}/collectives/{cid}/members",
            json={"endpoint_id": endpoint_id},
            headers=member_headers,
        )

    approved = client.post(
        f"{API}/collectives/{cid}/members/{ep_approve}/review",
        json={"decision": "approve"},
        headers=owner_headers,
    )
    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"

    rejected = client.post(
        f"{API}/collectives/{cid}/members/{ep_reject}/review",
        json={"decision": "reject"},
        headers=owner_headers,
    )
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "rejected"

    assert client.get(f"{API}/collectives/{cid}").json()["member_count"] == 1


def test_review_request_requires_collective_owner(
    client: TestClient, owner_headers: dict, member_headers: dict
) -> None:
    """A non-owner cannot review join requests."""
    collective = _create_collective(client, owner_headers, auto_approve=False)
    endpoint_id = _create_endpoint(client, member_headers, "my-model")
    client.post(
        f"{API}/collectives/{collective['id']}/members",
        json={"endpoint_id": endpoint_id},
        headers=member_headers,
    )

    resp = client.post(
        f"{API}/collectives/{collective['id']}/members/{endpoint_id}/review",
        json={"decision": "approve"},
        headers=member_headers,
    )
    assert resp.status_code == 403


# ----------------------------------------------------------------------
# Membership — invitations
# ----------------------------------------------------------------------


def test_invite_then_accept(
    client: TestClient, owner_headers: dict, member_headers: dict
) -> None:
    """An owner invites an endpoint; the endpoint owner accepts."""
    collective = _create_collective(client, owner_headers)
    cid = collective["id"]
    endpoint_id = _create_endpoint(client, member_headers, "invited-model")

    invited = client.post(
        f"{API}/collectives/{cid}/invitations",
        json={"endpoint_id": endpoint_id},
        headers=owner_headers,
    )
    assert invited.status_code == 201
    assert invited.json()["status"] == "invited"

    accepted = client.post(
        f"{API}/collectives/{cid}/invitations/{endpoint_id}/respond",
        json={"decision": "accept"},
        headers=member_headers,
    )
    assert accepted.status_code == 200
    assert accepted.json()["status"] == "approved"


def test_invite_then_decline(
    client: TestClient, owner_headers: dict, member_headers: dict
) -> None:
    """The endpoint owner can decline an invitation."""
    collective = _create_collective(client, owner_headers)
    cid = collective["id"]
    endpoint_id = _create_endpoint(client, member_headers, "declined-model")

    client.post(
        f"{API}/collectives/{cid}/invitations",
        json={"endpoint_id": endpoint_id},
        headers=owner_headers,
    )
    declined = client.post(
        f"{API}/collectives/{cid}/invitations/{endpoint_id}/respond",
        json={"decision": "decline"},
        headers=member_headers,
    )
    assert declined.status_code == 200
    assert declined.json()["status"] == "rejected"


def test_invite_requires_collective_owner(
    client: TestClient, owner_headers: dict, member_headers: dict
) -> None:
    """A non-owner cannot send invitations."""
    collective = _create_collective(client, owner_headers)
    endpoint_id = _create_endpoint(client, member_headers, "my-model")

    resp = client.post(
        f"{API}/collectives/{collective['id']}/invitations",
        json={"endpoint_id": endpoint_id},
        headers=member_headers,
    )
    assert resp.status_code == 403


def test_only_endpoint_owner_responds_to_invitation(
    client: TestClient, owner_headers: dict, member_headers: dict
) -> None:
    """Only the endpoint's owner can accept/decline its invitation."""
    collective = _create_collective(client, owner_headers)
    cid = collective["id"]
    endpoint_id = _create_endpoint(client, member_headers, "my-model")
    client.post(
        f"{API}/collectives/{cid}/invitations",
        json={"endpoint_id": endpoint_id},
        headers=owner_headers,
    )

    resp = client.post(
        f"{API}/collectives/{cid}/invitations/{endpoint_id}/respond",
        json={"decision": "accept"},
        headers=owner_headers,
    )
    assert resp.status_code == 403


# ----------------------------------------------------------------------
# Membership — listing and removal
# ----------------------------------------------------------------------


def test_list_members_hides_pending_from_non_owner(
    client: TestClient, owner_headers: dict, member_headers: dict
) -> None:
    """Pending memberships are visible to the owner but not to others."""
    collective = _create_collective(client, owner_headers, auto_approve=False)
    cid = collective["id"]
    endpoint_id = _create_endpoint(client, member_headers, "my-model")
    client.post(
        f"{API}/collectives/{cid}/members",
        json={"endpoint_id": endpoint_id},
        headers=member_headers,
    )

    anon = client.get(f"{API}/collectives/{cid}/members")
    assert anon.status_code == 200
    assert anon.json() == []

    owner_view = client.get(
        f"{API}/collectives/{cid}/members?status=pending", headers=owner_headers
    )
    assert owner_view.status_code == 200
    assert len(owner_view.json()) == 1

    forbidden = client.get(
        f"{API}/collectives/{cid}/members?status=pending", headers=member_headers
    )
    assert forbidden.status_code == 403


def test_list_members_hides_private_endpoints(
    client: TestClient, owner_headers: dict, member_headers: dict
) -> None:
    """An approved private endpoint is not exposed to unrelated viewers."""
    collective = _create_collective(client, owner_headers, auto_approve=True)
    cid = collective["id"]
    private_id = _create_endpoint(
        client, member_headers, "secret-model", visibility="private"
    )
    client.post(
        f"{API}/collectives/{cid}/members",
        json={"endpoint_id": private_id},
        headers=member_headers,
    )

    # The endpoint owner sees their own membership.
    owner_of_endpoint = client.get(
        f"{API}/collectives/{cid}/members", headers=member_headers
    )
    assert [m["endpoint_id"] for m in owner_of_endpoint.json()] == [private_id]

    # An anonymous viewer does not.
    assert client.get(f"{API}/collectives/{cid}/members").json() == []


def test_remove_member_by_endpoint_owner(
    client: TestClient, owner_headers: dict, member_headers: dict
) -> None:
    """An endpoint owner can remove (leave) their own membership."""
    collective = _create_collective(client, owner_headers, auto_approve=True)
    cid = collective["id"]
    endpoint_id = _create_endpoint(client, member_headers, "my-model")
    client.post(
        f"{API}/collectives/{cid}/members",
        json={"endpoint_id": endpoint_id},
        headers=member_headers,
    )

    removed = client.delete(
        f"{API}/collectives/{cid}/members/{endpoint_id}", headers=member_headers
    )
    assert removed.status_code == 204
    assert client.get(f"{API}/collectives/{cid}").json()["member_count"] == 0
