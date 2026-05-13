"""Tests for the runner-side SessionAPI attachment surface.

Run with: pytest sdk/golang/syfthubapi/containermode/runner/test_session_attachments.py
"""

from __future__ import annotations

import base64
import hashlib
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))

from session import Session, SessionAPI, SessionManager  # noqa: E402


def _noop_handler(session):
    """Dummy handler used to satisfy SessionManager constructor."""
    pass


def _new_session(attachments_dir: str = "") -> tuple[Session, SessionAPI]:
    s = Session(
        id="sess-1",
        prompt="hi",
        messages=[],
        config={},
        handler=_noop_handler,
        attachments_dir=attachments_dir,
    )
    return s, SessionAPI(s)


def test_attachments_dir_exposed_on_api():
    s, api = _new_session(attachments_dir="/tmp/x")
    assert api.attachments_dir == "/tmp/x"


def test_send_attachment_emits_inline_event(tmp_path):
    path = tmp_path / "hello.txt"
    body = b"hello world"
    path.write_bytes(body)
    s, api = _new_session(attachments_dir=str(tmp_path))
    fid = api.send_attachment(str(path), mime="text/plain", name="hello.txt")
    assert fid.startswith("att-")

    # The event was placed on the event queue.
    event = s.event_queue.get(timeout=1.0)
    assert event["type"] == "agent.attachment"
    data = event["data"]
    assert data["file_id"] == fid
    assert data["name"] == "hello.txt"
    assert data["mime"] == "text/plain"
    assert data["size_bytes"] == len(body)
    assert data["plaintext_sha256"] == hashlib.sha256(body).hexdigest()
    assert data["transport"] == "inline"
    assert base64.b64decode(data["inline_data_b64"]) == body


def test_send_attachment_missing_file_raises():
    s, api = _new_session()
    with pytest.raises(FileNotFoundError):
        api.send_attachment("/no/such/file.bin")


def test_receive_attachment_returns_none_on_timeout():
    s, api = _new_session()
    assert api.receive_attachment(timeout=0.05) is None


def test_deliver_attachment_routes_to_session_queue():
    s, api = _new_session()
    payload = {"file_id": "att-x", "name": "x.bin", "mime": "image/png", "path": "/tmp/x"}
    assert s.deliver_attachment(payload) is True
    got = api.receive_attachment(timeout=1.0)
    assert got == payload


def test_session_manager_deliver_attachment_unknown_session():
    mgr = SessionManager(_noop_handler)
    assert mgr.deliver_attachment("nope", {}) is False


def test_session_manager_start_propagates_attachments_dir():
    mgr = SessionManager(_noop_handler)
    sess = mgr.start_session(
        session_id="s",
        prompt="",
        messages=[],
        config={},
        attachments_dir="/tmp/atts",
    )
    assert sess.attachments_dir == "/tmp/atts"
    # cancel to ensure cleanup
    sess.cancel()
