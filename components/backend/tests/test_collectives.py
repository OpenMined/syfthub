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
    client: TestClient,
    headers: dict,
    name: str,
    visibility: str = "public",
    endpoint_type: str = "data_source",
) -> int:
    """Create an endpoint and return its ID.

    Defaults to ``data_source`` because only data-source endpoints are eligible
    to join a collective — most membership tests need a joinable endpoint.
    """
    resp = client.post(
        f"{API}/endpoints",
        json={
            "name": name,
            "type": endpoint_type,
            "visibility": visibility,
            "description": f"{name} description",
        },
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
        about="# ML Models\n\nLong-form markdown docs.",
        tags=["nlp", "vision"],
    )
    assert body["slug"] == "ml-models"
    # The shared-endpoint path is the unique 'collective/<slug>' identifier.
    assert body["shared_endpoint_path"] == "collective/ml-models"
    assert body["description"] == "Curated models"
    assert body["about"] == "# ML Models\n\nLong-form markdown docs."
    assert body["auto_approve"] is False
    assert body["member_count"] == 0
    assert body["owner_count"] == 0
    assert sorted(body["tags"]) == ["nlp", "vision"]
    # Verification is a platform-granted trust signal — never set on creation.
    assert body["verified"] is False


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

    # The shared-endpoint path survives every read path (id, slug, list).
    expected_path = f"collective/{created['slug']}"
    assert by_id.json()["shared_endpoint_path"] == expected_path
    assert by_slug.json()["shared_endpoint_path"] == expected_path
    listed = next(c for c in listing.json() if c["id"] == created["id"])
    assert listed["shared_endpoint_path"] == expected_path


def test_list_collectives_search(client: TestClient, owner_headers: dict) -> None:
    """The list endpoint filters by name, description and tags via ``search``."""
    genomics = _create_collective(
        client,
        owner_headers,
        name="Genomics Research",
        description="Sequencing data",
        tags=["healthcare", "dna"],
    )
    weather = _create_collective(
        client,
        owner_headers,
        name="Weather Models",
        description="Climate forecasting",
        tags=["climate"],
    )

    # Match by name.
    by_name = client.get(f"{API}/collectives", params={"search": "genomics"})
    assert by_name.status_code == 200
    ids = [c["id"] for c in by_name.json()]
    assert genomics["id"] in ids
    assert weather["id"] not in ids

    # Match by description.
    by_desc = client.get(f"{API}/collectives", params={"search": "forecasting"})
    assert [c["id"] for c in by_desc.json()] == [weather["id"]]

    # Match by tag.
    by_tag = client.get(f"{API}/collectives", params={"search": "healthcare"})
    assert genomics["id"] in [c["id"] for c in by_tag.json()]

    # A non-matching query returns no rows.
    none = client.get(f"{API}/collectives", params={"search": "nonexistent-xyz"})
    assert none.json() == []


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
        json={
            "description": "updated",
            "about": "## Updated docs",
            "auto_approve": True,
        },
        headers=owner_headers,
    )
    assert ok.status_code == 200
    assert ok.json()["description"] == "updated"
    assert ok.json()["about"] == "## Updated docs"
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
    body = resp.json()
    assert body["status"] == "pending"
    # The membership response carries the endpoint's identity for the UI.
    assert body["endpoint_slug"] == "my-model"
    assert body["endpoint_name"]
    assert body["endpoint_description"] == "my-model description"
    assert body["endpoint_owner_username"] == "member"
    assert body["endpoint_owner_full_name"] == "Member User"


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
    assert detail.json()["owner_count"] == 1


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


def test_get_invitation_readable_by_endpoint_owner(
    client: TestClient, owner_headers: dict, member_headers: dict
) -> None:
    """The endpoint owner can fetch their own invitation row to render the
    response landing page (list_members hides non-approved from non-managers)."""
    collective = _create_collective(client, owner_headers)
    cid = collective["id"]
    endpoint_id = _create_endpoint(client, member_headers, "inv-target")
    client.post(
        f"{API}/collectives/{cid}/invitations",
        json={"endpoint_id": endpoint_id},
        headers=owner_headers,
    )

    resp = client.get(
        f"{API}/collectives/{cid}/invitations/{endpoint_id}",
        headers=member_headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "invited"
    assert body["endpoint_id"] == endpoint_id


def test_get_invitation_readable_by_collective_owner(
    client: TestClient, owner_headers: dict, member_headers: dict
) -> None:
    """The collective owner who sent the invitation can also read the row."""
    collective = _create_collective(client, owner_headers)
    cid = collective["id"]
    endpoint_id = _create_endpoint(client, member_headers, "inv-target")
    client.post(
        f"{API}/collectives/{cid}/invitations",
        json={"endpoint_id": endpoint_id},
        headers=owner_headers,
    )

    resp = client.get(
        f"{API}/collectives/{cid}/invitations/{endpoint_id}",
        headers=owner_headers,
    )
    assert resp.status_code == 200, resp.text


def test_get_invitation_forbidden_for_outsider(client: TestClient) -> None:
    """A user who is neither the endpoint owner nor the collective owner is
    refused with 403."""
    owner = _register_and_login(client, "co-owner")
    ep_owner = _register_and_login(client, "ep-owner")
    outsider = _register_and_login(client, "nobody")

    collective = _create_collective(client, owner)
    cid = collective["id"]
    endpoint_id = _create_endpoint(client, ep_owner, "inv-target")
    client.post(
        f"{API}/collectives/{cid}/invitations",
        json={"endpoint_id": endpoint_id},
        headers=owner,
    )

    resp = client.get(
        f"{API}/collectives/{cid}/invitations/{endpoint_id}",
        headers=outsider,
    )
    assert resp.status_code == 403


def test_get_invitation_404_when_missing(
    client: TestClient, owner_headers: dict, member_headers: dict
) -> None:
    """No invitation row → 404, even when caller is otherwise authorized."""
    collective = _create_collective(client, owner_headers)
    cid = collective["id"]
    endpoint_id = _create_endpoint(client, member_headers, "never-invited")

    resp = client.get(
        f"{API}/collectives/{cid}/invitations/{endpoint_id}",
        headers=owner_headers,
    )
    assert resp.status_code == 404


def test_invite_endpoint_by_path(
    client: TestClient, owner_headers: dict, member_headers: dict
) -> None:
    """Invite-by-path resolves owner/slug and creates the same invited row
    that the numeric-id route would."""
    collective = _create_collective(client, owner_headers)
    cid = collective["id"]
    endpoint_id = _create_endpoint(client, member_headers, "by-path-target")

    resp = client.post(
        f"{API}/collectives/{cid}/invitations/by-path",
        json={"owner_username": "member", "slug": "by-path-target"},
        headers=owner_headers,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == "invited"
    assert body["endpoint_id"] == endpoint_id


def test_invite_by_path_404_when_endpoint_missing(
    client: TestClient, owner_headers: dict
) -> None:
    """Invite-by-path returns 404 when the path doesn't resolve."""
    collective = _create_collective(client, owner_headers)
    cid = collective["id"]
    resp = client.post(
        f"{API}/collectives/{cid}/invitations/by-path",
        json={"owner_username": "nobody", "slug": "nothing"},
        headers=owner_headers,
    )
    assert resp.status_code == 404


def test_invite_by_path_rejects_private_endpoint(
    client: TestClient, owner_headers: dict, member_headers: dict
) -> None:
    """Invite-by-path only resolves public endpoints — private endpoints are
    not discoverable via owner/slug so the route refuses them with 404."""
    collective = _create_collective(client, owner_headers)
    cid = collective["id"]
    _create_endpoint(client, member_headers, "secret-data", visibility="private")
    resp = client.post(
        f"{API}/collectives/{cid}/invitations/by-path",
        json={"owner_username": "member", "slug": "secret-data"},
        headers=owner_headers,
    )
    assert resp.status_code == 404


def test_invite_by_path_requires_collective_owner(
    client: TestClient, owner_headers: dict, member_headers: dict
) -> None:
    """A non-owner cannot invite via the path-based route either."""
    collective = _create_collective(client, owner_headers)
    cid = collective["id"]
    _create_endpoint(client, member_headers, "by-path-target")

    resp = client.post(
        f"{API}/collectives/{cid}/invitations/by-path",
        json={"owner_username": "member", "slug": "by-path-target"},
        headers=member_headers,
    )
    assert resp.status_code == 403


# ----------------------------------------------------------------------
# Membership — endpoint type eligibility (data sources only)
# ----------------------------------------------------------------------


def test_model_endpoint_cannot_request_join(
    client: TestClient, owner_headers: dict, member_headers: dict
) -> None:
    """A model-only endpoint is rejected from joining; no membership is created."""
    collective = _create_collective(client, owner_headers, auto_approve=True)
    cid = collective["id"]
    endpoint_id = _create_endpoint(
        client, member_headers, "a-model", endpoint_type="model"
    )

    resp = client.post(
        f"{API}/collectives/{cid}/members",
        json={"endpoint_id": endpoint_id},
        headers=member_headers,
    )
    assert resp.status_code == 400, resp.text
    assert "data source" in resp.json()["detail"].lower()

    # The rejected request must not leave a membership row behind.
    assert client.get(f"{API}/collectives/{cid}").json()["member_count"] == 0
    owner_view = client.get(f"{API}/collectives/{cid}/members", headers=owner_headers)
    assert owner_view.json() == []


def test_agent_endpoint_cannot_request_join(
    client: TestClient, owner_headers: dict, member_headers: dict
) -> None:
    """An agent endpoint cannot join a collective."""
    collective = _create_collective(client, owner_headers, auto_approve=True)
    endpoint_id = _create_endpoint(
        client, member_headers, "an-agent", endpoint_type="agent"
    )

    resp = client.post(
        f"{API}/collectives/{collective['id']}/members",
        json={"endpoint_id": endpoint_id},
        headers=member_headers,
    )
    assert resp.status_code == 400, resp.text


def test_data_source_endpoint_can_request_join(
    client: TestClient, owner_headers: dict, member_headers: dict
) -> None:
    """A plain data_source endpoint is eligible to join."""
    collective = _create_collective(client, owner_headers, auto_approve=True)
    endpoint_id = _create_endpoint(
        client, member_headers, "a-data-source", endpoint_type="data_source"
    )

    resp = client.post(
        f"{API}/collectives/{collective['id']}/members",
        json={"endpoint_id": endpoint_id},
        headers=member_headers,
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["status"] == "approved"


def test_model_data_source_endpoint_can_request_join(
    client: TestClient, owner_headers: dict, member_headers: dict
) -> None:
    """A model_data_source endpoint is eligible — it also exposes a data source."""
    collective = _create_collective(client, owner_headers, auto_approve=True)
    endpoint_id = _create_endpoint(
        client, member_headers, "hybrid", endpoint_type="model_data_source"
    )

    resp = client.post(
        f"{API}/collectives/{collective['id']}/members",
        json={"endpoint_id": endpoint_id},
        headers=member_headers,
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["status"] == "approved"


def test_model_endpoint_cannot_be_invited(
    client: TestClient, owner_headers: dict, member_headers: dict
) -> None:
    """A collective owner cannot invite a model-only endpoint."""
    collective = _create_collective(client, owner_headers)
    cid = collective["id"]
    endpoint_id = _create_endpoint(
        client, member_headers, "a-model", endpoint_type="model"
    )

    resp = client.post(
        f"{API}/collectives/{cid}/invitations",
        json={"endpoint_id": endpoint_id},
        headers=owner_headers,
    )
    assert resp.status_code == 400, resp.text
    assert "data source" in resp.json()["detail"].lower()

    # No invitation row, so the endpoint owner has nothing to respond to.
    owner_view = client.get(f"{API}/collectives/{cid}/members", headers=owner_headers)
    assert owner_view.json() == []


def test_agent_endpoint_cannot_be_invited(
    client: TestClient, owner_headers: dict, member_headers: dict
) -> None:
    """A collective owner cannot invite an agent endpoint."""
    collective = _create_collective(client, owner_headers)
    endpoint_id = _create_endpoint(
        client, member_headers, "an-agent", endpoint_type="agent"
    )

    resp = client.post(
        f"{API}/collectives/{collective['id']}/invitations",
        json={"endpoint_id": endpoint_id},
        headers=owner_headers,
    )
    assert resp.status_code == 400, resp.text


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


# ----------------------------------------------------------------------
# Invitation notification emails
# ----------------------------------------------------------------------


def test_invite_sends_notification_email(
    client: TestClient,
    owner_headers: dict,
    member_headers: dict,
    monkeypatch,
) -> None:
    """Inviting an endpoint schedules a notification email to its owner."""
    sent: list = []
    monkeypatch.setattr(
        "syfthub.api.endpoints.collectives.send_collective_invitation_email",
        lambda ctx: sent.append(ctx),
    )
    collective = _create_collective(client, owner_headers, name="ML Models")
    endpoint_id = _create_endpoint(client, member_headers, "invited-model")

    resp = client.post(
        f"{API}/collectives/{collective['id']}/invitations",
        json={"endpoint_id": endpoint_id},
        headers=owner_headers,
    )
    assert resp.status_code == 201

    assert len(sent) == 1
    ctx = sent[0]
    assert ctx.to_email == "member@example.com"
    assert ctx.collective_slug == collective["slug"]
    assert ctx.endpoint_id == endpoint_id
    assert ctx.endpoint_name == "invited-model"


def test_invite_approving_join_request_sends_no_email(
    client: TestClient,
    owner_headers: dict,
    member_headers: dict,
    monkeypatch,
) -> None:
    """When an invite only approves a standing join request, no email is sent."""
    sent: list = []
    monkeypatch.setattr(
        "syfthub.api.endpoints.collectives.send_collective_invitation_email",
        lambda ctx: sent.append(ctx),
    )
    collective = _create_collective(client, owner_headers, auto_approve=False)
    cid = collective["id"]
    endpoint_id = _create_endpoint(client, member_headers, "my-model")
    # The endpoint requests to join first -> pending.
    client.post(
        f"{API}/collectives/{cid}/members",
        json={"endpoint_id": endpoint_id},
        headers=member_headers,
    )
    # Owner invites that same endpoint -> approves it, no invitation email.
    resp = client.post(
        f"{API}/collectives/{cid}/invitations",
        json={"endpoint_id": endpoint_id},
        headers=owner_headers,
    )
    assert resp.status_code == 201
    assert resp.json()["status"] == "approved"
    assert sent == []


def test_invite_own_endpoint_sends_no_email(
    client: TestClient, owner_headers: dict, monkeypatch
) -> None:
    """Inviting an endpoint you own yourself does not email you."""
    sent: list = []
    monkeypatch.setattr(
        "syfthub.api.endpoints.collectives.send_collective_invitation_email",
        lambda ctx: sent.append(ctx),
    )
    collective = _create_collective(client, owner_headers)
    endpoint_id = _create_endpoint(client, owner_headers, "my-own-model")

    resp = client.post(
        f"{API}/collectives/{collective['id']}/invitations",
        json={"endpoint_id": endpoint_id},
        headers=owner_headers,
    )
    assert resp.status_code == 201
    assert resp.json()["status"] == "invited"
    assert sent == []


def test_invitation_email_template_renders_accept_link() -> None:
    """The invitation email template embeds the accept/decline link and names."""
    from syfthub.services.email_service import _invitation_template

    url = "https://hub.example.com/collectives/ml-models/invitations/7"
    html = _invitation_template.render(
        recipient_name="Dev User",
        inviter_name="Admin User",
        collective_name="ML Models",
        endpoint_name="my-model",
        invite_url=url,
    )
    assert url in html
    assert "Admin User" in html
    assert "ML Models" in html
    assert "my-model" in html


# ----------------------------------------------------------------------
# Endpoint paths
# ----------------------------------------------------------------------


def test_get_collective_endpoint_paths_not_found(client: TestClient) -> None:
    """A missing collective slug returns 404 from the endpoint-paths route."""
    resp = client.get(f"{API}/collectives/by-slug/no-such-slug/endpoint-paths")
    assert resp.status_code == 404, resp.text


def test_get_collective_endpoint_paths_empty(
    client: TestClient, owner_headers: dict
) -> None:
    """A collective with no members returns an empty list of endpoint paths."""
    collective = _create_collective(client, owner_headers, auto_approve=True)
    slug = collective["slug"]

    resp = client.get(f"{API}/collectives/by-slug/{slug}/endpoint-paths")
    assert resp.status_code == 200, resp.text
    assert resp.json() == [], f"Expected [] but got {resp.json()}"


def test_get_collective_endpoint_paths_approved_only(
    client: TestClient, owner_headers: dict
) -> None:
    """Only approved memberships appear in the endpoint-paths response."""
    contributor_headers = _register_and_login(client, "contributor")
    collective = _create_collective(client, owner_headers, auto_approve=False)
    cid = collective["id"]
    slug = collective["slug"]

    ep_approved = _create_endpoint(client, contributor_headers, "approved-ds")
    ep_pending = _create_endpoint(client, contributor_headers, "pending-ds")
    ep_rejected = _create_endpoint(client, contributor_headers, "rejected-ds")

    # All three request to join.
    for ep_id in (ep_approved, ep_pending, ep_rejected):
        client.post(
            f"{API}/collectives/{cid}/members",
            json={"endpoint_id": ep_id},
            headers=contributor_headers,
        )

    # Owner approves one and rejects one; pending-ds is left untouched.
    client.post(
        f"{API}/collectives/{cid}/members/{ep_approved}/review",
        json={"decision": "approve"},
        headers=owner_headers,
    )
    client.post(
        f"{API}/collectives/{cid}/members/{ep_rejected}/review",
        json={"decision": "reject"},
        headers=owner_headers,
    )

    resp = client.get(f"{API}/collectives/by-slug/{slug}/endpoint-paths")
    assert resp.status_code == 200, resp.text
    paths = resp.json()
    assert paths == ["contributor/approved-ds"], (
        f"Expected only the approved path but got {paths}"
    )


def test_get_collective_endpoint_paths_format(
    client: TestClient, owner_headers: dict, member_headers: dict
) -> None:
    """Approved members are returned as 'owner/slug' strings in any order."""
    collective = _create_collective(client, owner_headers, auto_approve=True)
    cid = collective["id"]
    slug = collective["slug"]

    ep_one = _create_endpoint(client, member_headers, "source-one")
    ep_two = _create_endpoint(client, member_headers, "source-two")

    for ep_id in (ep_one, ep_two):
        client.post(
            f"{API}/collectives/{cid}/members",
            json={"endpoint_id": ep_id},
            headers=member_headers,
        )

    resp = client.get(f"{API}/collectives/by-slug/{slug}/endpoint-paths")
    assert resp.status_code == 200, resp.text
    paths = resp.json()

    assert "member/source-one" in paths, f"'member/source-one' missing from {paths}"
    assert "member/source-two" in paths, f"'member/source-two' missing from {paths}"

    # Every item must match the "owner/slug" format.
    for path in paths:
        parts = path.split("/")
        assert len(parts) == 2 and all(parts), (
            f"Path {path!r} does not match 'owner/slug' format"
        )


# ----------------------------------------------------------------------
# Shared endpoints — named, curated subsets of approved members
# ----------------------------------------------------------------------


def _approve_endpoint_into_collective(
    client: TestClient,
    *,
    collective_id: int,
    endpoint_id: int,
    member_headers: dict,
    owner_headers: dict,
) -> None:
    """End-to-end helper: request join + owner approves, leaving status=approved."""
    resp = client.post(
        f"{API}/collectives/{collective_id}/members",
        json={"endpoint_id": endpoint_id},
        headers=member_headers,
    )
    assert resp.status_code == 201, resp.text
    resp = client.post(
        f"{API}/collectives/{collective_id}/members/{endpoint_id}/review",
        json={"decision": "approve"},
        headers=owner_headers,
    )
    assert resp.status_code == 200, resp.text


@pytest.fixture
def collective_with_two_members(
    client: TestClient, owner_headers: dict, member_headers: dict
) -> dict:
    """A collective with two approved data-source endpoints from a separate user.

    Yields a dict carrying the collective id/slug and the two approved endpoint
    ids so each shared-endpoint test can curate subsets without rebuilding the
    base graph.
    """
    collective = _create_collective(client, owner_headers, name="Genomics Collective")
    endpoint_one = _create_endpoint(client, member_headers, name="Source One")
    endpoint_two = _create_endpoint(client, member_headers, name="Source Two")
    for endpoint_id in (endpoint_one, endpoint_two):
        _approve_endpoint_into_collective(
            client,
            collective_id=collective["id"],
            endpoint_id=endpoint_id,
            member_headers=member_headers,
            owner_headers=owner_headers,
        )
    return {
        "id": collective["id"],
        "slug": collective["slug"],
        "endpoint_one": endpoint_one,
        "endpoint_two": endpoint_two,
    }


def test_create_shared_endpoint(
    client: TestClient,
    owner_headers: dict,
    collective_with_two_members: dict,
) -> None:
    """Owner creates a shared endpoint with one of two approved members."""
    collective = collective_with_two_members
    resp = client.post(
        f"{API}/collectives/{collective['id']}/shared-endpoints",
        json={
            "name": "Health News",
            "description": "Subset focused on health",
            "endpoint_ids": [collective["endpoint_one"]],
        },
        headers=owner_headers,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["name"] == "Health News"
    assert body["slug"] == "health-news"
    assert body["collective_slug"] == collective["slug"]
    assert (
        body["shared_endpoint_path"] == f"collective/{collective['slug']}/health-news"
    )
    assert body["member_count"] == 1
    assert body["active_member_count"] == 1
    assert len(body["members"]) == 1
    assert body["members"][0]["endpoint_id"] == collective["endpoint_one"]
    assert body["members"][0]["is_active"] is True


def test_create_shared_endpoint_explicit_slug(
    client: TestClient,
    owner_headers: dict,
    collective_with_two_members: dict,
) -> None:
    """Explicit slug is honored when valid."""
    collective = collective_with_two_members
    resp = client.post(
        f"{API}/collectives/{collective['id']}/shared-endpoints",
        json={
            "name": "Curated",
            "slug": "alpha",
            "endpoint_ids": [collective["endpoint_one"]],
        },
        headers=owner_headers,
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["slug"] == "alpha"


def test_reserved_slug_all_rejected(
    client: TestClient,
    owner_headers: dict,
    collective_with_two_members: dict,
) -> None:
    """The reserved 'all' slug cannot be used for a custom shared endpoint."""
    collective = collective_with_two_members
    resp = client.post(
        f"{API}/collectives/{collective['id']}/shared-endpoints",
        json={
            "name": "All Endpoints",
            "slug": "all",
            "endpoint_ids": [collective["endpoint_one"]],
        },
        headers=owner_headers,
    )
    assert resp.status_code == 422, resp.text


def test_duplicate_slug_per_collective_rejected(
    client: TestClient,
    owner_headers: dict,
    collective_with_two_members: dict,
) -> None:
    """Two shared endpoints in the same collective cannot share a slug."""
    collective = collective_with_two_members
    payload = {
        "name": "Health",
        "slug": "health",
        "endpoint_ids": [collective["endpoint_one"]],
    }
    resp = client.post(
        f"{API}/collectives/{collective['id']}/shared-endpoints",
        json=payload,
        headers=owner_headers,
    )
    assert resp.status_code == 201, resp.text
    resp = client.post(
        f"{API}/collectives/{collective['id']}/shared-endpoints",
        json=payload,
        headers=owner_headers,
    )
    assert resp.status_code == 409, resp.text


def test_non_approved_endpoint_rejected_on_create(
    client: TestClient,
    owner_headers: dict,
    member_headers: dict,
    collective_with_two_members: dict,
) -> None:
    """An endpoint that isn't an approved member can't be added to a subset."""
    collective = collective_with_two_members
    # A second collective with an endpoint that's NOT approved in the first one.
    outsider = _create_endpoint(client, member_headers, name="Outsider")
    resp = client.post(
        f"{API}/collectives/{collective['id']}/shared-endpoints",
        json={
            "name": "Bad",
            "endpoint_ids": [collective["endpoint_one"], outsider],
        },
        headers=owner_headers,
    )
    assert resp.status_code == 400, resp.text
    assert str(outsider) in resp.json()["detail"]


def test_empty_endpoint_ids_rejected(
    client: TestClient,
    owner_headers: dict,
    collective_with_two_members: dict,
) -> None:
    """A shared endpoint must have at least one configured member."""
    collective = collective_with_two_members
    resp = client.post(
        f"{API}/collectives/{collective['id']}/shared-endpoints",
        json={"name": "Empty", "endpoint_ids": []},
        headers=owner_headers,
    )
    assert resp.status_code == 422, resp.text


def test_create_requires_collective_owner(
    client: TestClient,
    member_headers: dict,
    collective_with_two_members: dict,
) -> None:
    """Non-owners cannot create shared endpoints."""
    collective = collective_with_two_members
    resp = client.post(
        f"{API}/collectives/{collective['id']}/shared-endpoints",
        json={
            "name": "Sneaky",
            "endpoint_ids": [collective["endpoint_one"]],
        },
        headers=member_headers,
    )
    assert resp.status_code == 403, resp.text


def test_list_and_get_shared_endpoints(
    client: TestClient,
    owner_headers: dict,
    collective_with_two_members: dict,
) -> None:
    """List + get-by-slug return the created shared endpoints."""
    collective = collective_with_two_members
    resp = client.post(
        f"{API}/collectives/{collective['id']}/shared-endpoints",
        json={
            "name": "Health News",
            "endpoint_ids": [collective["endpoint_one"]],
        },
        headers=owner_headers,
    )
    assert resp.status_code == 201, resp.text

    # By collective id (public-readable).
    resp = client.get(f"{API}/collectives/{collective['id']}/shared-endpoints")
    assert resp.status_code == 200
    assert len(resp.json()) == 1

    # By collective slug (public-readable).
    resp = client.get(
        f"{API}/collectives/by-slug/{collective['slug']}/shared-endpoints"
    )
    assert resp.status_code == 200
    assert len(resp.json()) == 1

    # By slug pair.
    resp = client.get(
        f"{API}/collectives/by-slug/{collective['slug']}/shared-endpoints/health-news"
    )
    assert resp.status_code == 200
    assert resp.json()["slug"] == "health-news"


def test_update_shared_endpoint_replaces_members(
    client: TestClient,
    owner_headers: dict,
    collective_with_two_members: dict,
) -> None:
    """PATCH with endpoint_ids replaces the full member set."""
    collective = collective_with_two_members
    create = client.post(
        f"{API}/collectives/{collective['id']}/shared-endpoints",
        json={
            "name": "Curated",
            "endpoint_ids": [collective["endpoint_one"]],
        },
        headers=owner_headers,
    )
    assert create.status_code == 201

    resp = client.patch(
        f"{API}/collectives/{collective['id']}/shared-endpoints/curated",
        json={
            "name": "Curated v2",
            "endpoint_ids": [collective["endpoint_two"]],
        },
        headers=owner_headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["name"] == "Curated v2"
    assert body["member_count"] == 1
    assert body["members"][0]["endpoint_id"] == collective["endpoint_two"]


def test_update_shared_endpoint_omitting_endpoints_leaves_members(
    client: TestClient,
    owner_headers: dict,
    collective_with_two_members: dict,
) -> None:
    """Omitting endpoint_ids in PATCH leaves the membership untouched."""
    collective = collective_with_two_members
    client.post(
        f"{API}/collectives/{collective['id']}/shared-endpoints",
        json={
            "name": "Curated",
            "endpoint_ids": [
                collective["endpoint_one"],
                collective["endpoint_two"],
            ],
        },
        headers=owner_headers,
    )
    resp = client.patch(
        f"{API}/collectives/{collective['id']}/shared-endpoints/curated",
        json={"description": "Just a description tweak"},
        headers=owner_headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["member_count"] == 2


def test_delete_shared_endpoint(
    client: TestClient,
    owner_headers: dict,
    collective_with_two_members: dict,
) -> None:
    """Owner can delete; subsequent GET returns 404."""
    collective = collective_with_two_members
    client.post(
        f"{API}/collectives/{collective['id']}/shared-endpoints",
        json={"name": "Bye", "endpoint_ids": [collective["endpoint_one"]]},
        headers=owner_headers,
    )
    resp = client.delete(
        f"{API}/collectives/{collective['id']}/shared-endpoints/bye",
        headers=owner_headers,
    )
    assert resp.status_code == 204, resp.text
    resp = client.get(f"{API}/collectives/{collective['id']}/shared-endpoints/bye")
    assert resp.status_code == 404


def test_endpoint_paths_intersect_with_approved(
    client: TestClient,
    owner_headers: dict,
    member_headers: dict,
    collective_with_two_members: dict,
) -> None:
    """When a configured endpoint is removed from the collective, it drops from fan-out."""
    collective = collective_with_two_members
    client.post(
        f"{API}/collectives/{collective['id']}/shared-endpoints",
        json={
            "name": "Both",
            "endpoint_ids": [
                collective["endpoint_one"],
                collective["endpoint_two"],
            ],
        },
        headers=owner_headers,
    )

    # Sanity check: both members are in the fan-out before removal.
    resp = client.get(
        f"{API}/collectives/by-slug/{collective['slug']}"
        f"/shared-endpoints/both/endpoint-paths"
    )
    assert resp.status_code == 200, resp.text
    assert sorted(resp.json()) == ["member/source-one", "member/source-two"]

    # Endpoint owner leaves the collective with endpoint_two.
    resp = client.delete(
        f"{API}/collectives/{collective['id']}/members/{collective['endpoint_two']}",
        headers=member_headers,
    )
    assert resp.status_code == 204, resp.text

    # endpoint_two silently drops from the shared endpoint at resolve time.
    resp = client.get(
        f"{API}/collectives/by-slug/{collective['slug']}"
        f"/shared-endpoints/both/endpoint-paths"
    )
    assert resp.status_code == 200, resp.text
    assert resp.json() == ["member/source-one"]

    # The shared-endpoint detail surfaces the inactive state in `members`.
    resp = client.get(
        f"{API}/collectives/by-slug/{collective['slug']}/shared-endpoints/both"
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["member_count"] == 2
    assert body["active_member_count"] == 1
    inactive = [m for m in body["members"] if not m["is_active"]]
    assert len(inactive) == 1
    assert inactive[0]["endpoint_id"] == collective["endpoint_two"]


def test_all_slug_resolves_to_full_membership(
    client: TestClient,
    collective_with_two_members: dict,
) -> None:
    """``collective/<X>/all`` and ``collective/<X>`` resolve identically."""
    collective = collective_with_two_members
    resp_all = client.get(
        f"{API}/collectives/by-slug/{collective['slug']}"
        f"/shared-endpoints/all/endpoint-paths"
    )
    resp_default = client.get(
        f"{API}/collectives/by-slug/{collective['slug']}/endpoint-paths"
    )
    assert resp_all.status_code == 200, resp_all.text
    assert resp_default.status_code == 200, resp_default.text
    assert sorted(resp_all.json()) == sorted(resp_default.json())


def test_unknown_shared_slug_404(
    client: TestClient,
    collective_with_two_members: dict,
) -> None:
    """Querying an unknown shared slug yields 404."""
    collective = collective_with_two_members
    resp = client.get(
        f"{API}/collectives/by-slug/{collective['slug']}"
        f"/shared-endpoints/does-not-exist/endpoint-paths"
    )
    assert resp.status_code == 404


def test_deleting_collective_cascades_to_shared_endpoints(
    client: TestClient,
    owner_headers: dict,
    collective_with_two_members: dict,
) -> None:
    """Cascade: deleting the collective removes its shared endpoints."""
    collective = collective_with_two_members
    client.post(
        f"{API}/collectives/{collective['id']}/shared-endpoints",
        json={"name": "Sub", "endpoint_ids": [collective["endpoint_one"]]},
        headers=owner_headers,
    )
    resp = client.delete(f"{API}/collectives/{collective['id']}", headers=owner_headers)
    assert resp.status_code == 204, resp.text
    # The parent is gone, so the by-slug lookup 404s.
    resp = client.get(
        f"{API}/collectives/by-slug/{collective['slug']}/shared-endpoints"
    )
    assert resp.status_code == 404


# ----------------------------------------------------------------------
# Regression tests for the post-review hardening pass
# ----------------------------------------------------------------------


def test_auto_derived_reserved_slug_falls_through(
    client: TestClient,
    owner_headers: dict,
    collective_with_two_members: dict,
) -> None:
    """A name that slugifies to a reserved slug must not persist as that slug.

    Without the resolver guard, ``name='All'`` would slugify to ``'all'`` and
    create an unaddressable subset (the resolver short-circuits on ``all``).
    Expect either a generated fallback slug (NOT in the reserved set) or a
    rejection — never the reserved slug itself.
    """
    collective = collective_with_two_members
    resp = client.post(
        f"{API}/collectives/{collective['id']}/shared-endpoints",
        json={
            "name": "All",
            "endpoint_ids": [collective["endpoint_one"]],
        },
        headers=owner_headers,
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["slug"] != "all"


def test_patch_explicit_null_description_rejected_as_422(
    client: TestClient,
    owner_headers: dict,
    collective_with_two_members: dict,
) -> None:
    """PATCH ``{"description": null}`` must 422, not 500.

    The DB column is NOT NULL; passing an explicit null used to bubble up as
    a generic 500 IntegrityError because the schema accepted ``Optional[str]
    = None`` as a valid explicit value.
    """
    collective = collective_with_two_members
    client.post(
        f"{API}/collectives/{collective['id']}/shared-endpoints",
        json={"name": "Doc", "endpoint_ids": [collective["endpoint_one"]]},
        headers=owner_headers,
    )
    resp = client.patch(
        f"{API}/collectives/{collective['id']}/shared-endpoints/doc",
        json={"description": None},
        headers=owner_headers,
    )
    assert resp.status_code == 422, resp.text

    resp = client.patch(
        f"{API}/collectives/{collective['id']}/shared-endpoints/doc",
        json={"name": None},
        headers=owner_headers,
    )
    assert resp.status_code == 422, resp.text


def test_bulk_list_shared_endpoints(
    client: TestClient,
    owner_headers: dict,
    collective_with_two_members: dict,
) -> None:
    """``GET /shared-endpoints/bulk`` returns rows across every requested collective.

    The chat-view modal relies on this endpoint to avoid the
    one-request-per-collective fan-out.
    """
    collective = collective_with_two_members
    # Create one shared endpoint to be discovered by the bulk read.
    create = client.post(
        f"{API}/collectives/{collective['id']}/shared-endpoints",
        json={"name": "First", "endpoint_ids": [collective["endpoint_one"]]},
        headers=owner_headers,
    )
    assert create.status_code == 201

    # An unknown id is silently skipped rather than 404ing the whole batch.
    resp = client.get(
        f"{API}/collectives/shared-endpoints/bulk",
        params=[("collective_id", collective["id"]), ("collective_id", 999_999)],
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body) == 1
    assert body[0]["slug"] == "first"
    assert body[0]["collective_id"] == collective["id"]


def test_bulk_list_empty_request(client: TestClient) -> None:
    """No ``collective_id`` query params → empty list (no 422)."""
    resp = client.get(f"{API}/collectives/shared-endpoints/bulk")
    assert resp.status_code == 200
    assert resp.json() == []
