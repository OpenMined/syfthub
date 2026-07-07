"""Canonical client-IP derivation for the backend.

There is exactly ONE trustworthy way to identify the caller behind our proxy,
and every per-IP decision (rate limiting, OTP abuse limits, audit trails,
request logs) must use it so they can't disagree or be individually spoofed.

Trust model (current deployment):
- nginx is the sole ingress / TLS terminator; the backend port is `expose`-only
  on the internal compose network, never published to the host.
- nginx sets ``X-Real-IP`` from ``$remote_addr`` with ``proxy_set_header``, which
  *overwrites* any client-supplied value — so ``X-Real-IP`` reaching the backend
  is the real client IP and cannot be forged by the caller.
- ``X-Forwarded-For`` is deliberately NOT trusted: nginx *appends* to it, so its
  leftmost entry is attacker-controlled. Reading it (as uvicorn's --proxy-headers
  or a naive `xff.split(",")[0]` would) makes any per-IP control bypassable.

CAVEAT: this assumes nginx remains the edge. If a CDN/load balancer is ever put
in front of nginx, ``$remote_addr`` becomes that intermediary's IP; nginx would
then need `set_real_ip_from` / `real_ip_header` so ``X-Real-IP`` stays the true
client.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from starlette.requests import Request


def get_client_ip(request: Request) -> str:
    """Return the trusted client IP for per-IP decisions.

    Prefers nginx's un-spoofable ``X-Real-IP`` header; falls back to the socket
    peer only when the header is absent (a direct/local request with no proxy).
    """
    real_ip = request.headers.get("x-real-ip")
    if real_ip:
        return real_ip.strip()
    if request.client and request.client.host:
        return request.client.host
    return "unknown"
