"""Tests for the canonical client-IP derivation (core/client_ip.py).

These lock in the security-critical property that every per-IP control depends
on: the caller's own ``X-Forwarded-For`` is never trusted, so a client cannot
choose which bucket it lands in. Only nginx's ``X-Real-IP`` (or the real socket
peer) is used.
"""

from unittest.mock import MagicMock

from syfthub.core.client_ip import get_client_ip


def _request(headers: dict[str, str] | None = None, client_host: str | None = None):
    req = MagicMock()
    req.headers = headers or {}
    if client_host is None:
        req.client = None
    else:
        req.client.host = client_host
    return req


def test_prefers_x_real_ip_over_socket_peer() -> None:
    req = _request(headers={"x-real-ip": "203.0.113.9"}, client_host="10.0.0.2")
    assert get_client_ip(req) == "203.0.113.9"


def test_x_forwarded_for_is_ignored() -> None:
    """A client-supplied X-Forwarded-For must NOT influence the derived IP.

    This is the spoofing vector: nginx appends to XFF, so its leftmost entry is
    attacker-controlled. Only the un-spoofable X-Real-IP (or socket peer) counts.
    """
    req = _request(
        headers={"x-forwarded-for": "1.2.3.4, 203.0.113.9"},
        client_host="10.0.0.2",
    )
    # XFF ignored entirely → falls through to the socket peer.
    assert get_client_ip(req) == "10.0.0.2"


def test_x_real_ip_wins_even_with_spoofed_forwarded_for() -> None:
    req = _request(
        headers={"x-forwarded-for": "1.2.3.4", "x-real-ip": "203.0.113.9"},
        client_host="10.0.0.2",
    )
    assert get_client_ip(req) == "203.0.113.9"


def test_falls_back_to_socket_peer_when_no_headers() -> None:
    assert get_client_ip(_request(client_host="10.0.0.2")) == "10.0.0.2"


def test_unknown_when_no_ip_available() -> None:
    assert get_client_ip(_request()) == "unknown"


def test_real_ip_is_stripped() -> None:
    req = _request(headers={"x-real-ip": "  203.0.113.9  "})
    assert get_client_ip(req) == "203.0.113.9"
