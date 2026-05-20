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
