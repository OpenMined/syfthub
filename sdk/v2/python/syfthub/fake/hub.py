"""A fake SyftHub: identity, discovery, satellite-token minting, MPP wallet pay."""
from __future__ import annotations

import hashlib
from typing import Any

from ..models import Endpoint, Selection
from . import data as D
from .space import World


class FakeHub:
    def __init__(self, world: World) -> None:
        self.world = world
        self.user: dict[str, Any] | None = None
        self.hub_wallet = D.USER["hub_wallet"]

    # identity ----------------------------------------------------------------
    def login(self, method: str, **kw: Any) -> dict[str, Any]:
        if method == "password" and kw.get("password") != "secret":
            raise PermissionError("Invalid username or password")
        self.user = dict(D.USER, auth=method)
        return self.user

    def logout(self) -> None:
        self.user = None

    # discovery ---------------------------------------------------------------
    def browse(self, type_: str | None = None) -> Selection:
        eps = [e for e in self.world.endpoints.values() if type_ in (None, e.type)]
        return Selection(sorted(eps, key=lambda e: -e.stars_count))

    def search(self, query: str, type_: str | None = None) -> Selection:
        q = query.lower().split()
        hits = [e for e in self.browse(type_)
                if any(w in (e.name + e.description + e.slug).lower() for w in q)]
        return Selection(hits or self.browse(type_)[:4])

    def get(self, path: str) -> Endpoint:
        return self.world.endpoints[path]

    def expand_collective(self, slug: str) -> list[str]:
        return D.COLLECTIVES.get(slug, [])

    # tokens ------------------------------------------------------------------
    def satellite_token(self, owner: str, resource: str, *, guest: bool = False) -> str:
        email = "guest@example.com" if guest or not self.user else self.user["email"]
        tok = "sat." + hashlib.sha1(f"{owner}|{resource}|{email}".encode()).hexdigest()[:16]
        self.world.tokens[tok] = email
        return tok

    # MPP: forward the Space's challenge to the Hub wallet, get an X-Payment credential
    def wallet_pay(self, www_authenticate: str, endpoint_slug: str, amount: float) -> str:
        if self.hub_wallet + 1e-9 < amount:
            raise ValueError(f"Hub wallet has {self.hub_wallet:.2f}, needs {amount:.2f}")
        self.hub_wallet = round(self.hub_wallet - amount, 6)
        cred = "Payment " + hashlib.sha256(www_authenticate.encode()).hexdigest()[:24]
        self.world.paid_credentials.add(cred)
        return cred
