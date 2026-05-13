"""Tests for the HTTP relay endpoints at /api/v1/agent/session/{sid}/attachment."""

from __future__ import annotations

import io
import secrets

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from aggregator.clients import nats_object_store
from aggregator.services import attachment_relay
from aggregator.services.attachment_session_state import (
    MAX_ATTACHMENT_BYTES_PER_FILE,
    AttachmentSession,
    registry,
)


class _FakeTransport:
    """In-process transport stand-in that records send_to_space calls instead
    of pushing through NATS."""

    def __init__(self) -> None:
        self.sent: list[dict] = []

    async def send_to_space(self, message: dict) -> None:
        self.sent.append(message)


@pytest.fixture
def app() -> FastAPI:
    a = FastAPI()
    a.include_router(attachment_relay.router)
    return a


@pytest.fixture
def session_id() -> str:
    return "sess-test-" + secrets.token_hex(4)


@pytest.fixture
def object_store_stub():
    """Substitute the JetStream Object Store singleton with an in-memory stub
    so tests don't need a real NATS server."""
    stub = nats_object_store.use_in_memory_stub_for_tests()
    yield stub
    nats_object_store.reset_for_tests()


@pytest.fixture
def fake_session(
    session_id: str,
    object_store_stub,  # noqa: ARG001 — fixture is order-dependent
) -> tuple[AttachmentSession, _FakeTransport]:
    """Register a fresh session in the global attachment-state registry."""
    transport = _FakeTransport()
    sess = AttachmentSession(
        session_id=session_id,
        target_username="alice",
        session_attachment_key=secrets.token_bytes(32),
        transport=transport,
    )
    registry().register(sess)
    yield sess, transport
    registry().unregister(session_id)
    attachment_relay.reset_for_tests()


def test_upload_returns_file_id_and_publishes_event(app, fake_session):
    sess, transport = fake_session
    client = TestClient(app)
    body = b"hello attachment world"
    resp = client.post(
        f"/agent/session/{sess.session_id}/attachment",
        files={"file": ("hello.txt", io.BytesIO(body), "text/plain")},
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["file_id"].startswith("att-")
    assert data["size_bytes"] == len(body)
    assert data["transport"] == "object_store"
    assert data["plaintext_sha256"]

    # The transport should have received a user.attachment metadata event.
    assert len(transport.sent) == 1
    event = transport.sent[0]
    assert event["type"] == "user.attachment"
    att = event["payload"]
    assert att["file_id"] == data["file_id"]
    assert att["transport"] == "object_store"
    assert att["wrapped_key"]["algorithm"] == "AES-256-GCM"
    assert att["wrapped_key"]["info"] == "syfthub-attachment-v1"
    assert att["chunk_size"] == 64 * 1024


def test_upload_for_unknown_session_returns_404(app):
    client = TestClient(app)
    resp = client.post(
        "/agent/session/no-such/attachment",
        files={"file": ("x.txt", io.BytesIO(b"hi"), "text/plain")},
    )
    assert resp.status_code == 404


def test_upload_rejects_oversize(app, fake_session):
    sess, _ = fake_session
    client = TestClient(app)
    body = b"x" * (MAX_ATTACHMENT_BYTES_PER_FILE + 1)
    resp = client.post(
        f"/agent/session/{sess.session_id}/attachment",
        files={"file": ("big.bin", io.BytesIO(body), "application/octet-stream")},
    )
    assert resp.status_code == 413


def test_upload_rejects_empty_body(app, fake_session):
    sess, _ = fake_session
    client = TestClient(app)
    resp = client.post(
        f"/agent/session/{sess.session_id}/attachment",
        files={"file": ("empty.bin", io.BytesIO(b""), "application/octet-stream")},
    )
    assert resp.status_code == 400


def test_download_round_trip(app, fake_session):
    sess, _ = fake_session
    client = TestClient(app)
    body = b"download me, please"
    up = client.post(
        f"/agent/session/{sess.session_id}/attachment",
        files={"file": ("dl.txt", io.BytesIO(body), "text/plain")},
    )
    assert up.status_code == 201
    file_id = up.json()["file_id"]

    dl = client.get(f"/agent/session/{sess.session_id}/attachment/{file_id}")
    assert dl.status_code == 200
    assert dl.content == body
    assert dl.headers["x-attachment-sha256"] == up.json()["plaintext_sha256"]


def test_download_for_unknown_session_returns_404(app):
    client = TestClient(app)
    resp = client.get("/agent/session/no-such/attachment/att-123")
    assert resp.status_code == 404


def test_download_for_unknown_file_returns_404(app, fake_session):
    sess, _ = fake_session
    client = TestClient(app)
    resp = client.get(f"/agent/session/{sess.session_id}/attachment/att-missing")
    assert resp.status_code == 404


def test_session_quota_blocks_after_limit_is_hit(app, fake_session, monkeypatch):
    sess, _ = fake_session
    # Tighten the per-session aggregate to a few bytes so the test is fast.
    monkeypatch.setattr(
        "aggregator.services.attachment_session_state.MAX_ATTACHMENT_BYTES_PER_SESSION",
        10,
    )
    client = TestClient(app)
    # First small upload — fits.
    r1 = client.post(
        f"/agent/session/{sess.session_id}/attachment",
        files={"file": ("a.txt", io.BytesIO(b"12345"), "text/plain")},
    )
    assert r1.status_code == 201
    # Second upload — pushes past the 10-byte session limit.
    r2 = client.post(
        f"/agent/session/{sess.session_id}/attachment",
        files={"file": ("b.txt", io.BytesIO(b"6789012345"), "text/plain")},
    )
    assert r2.status_code == 429
