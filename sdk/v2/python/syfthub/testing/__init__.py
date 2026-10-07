"""Test doubles. ``MockTransport`` implements the SDK's transport seam over in-memory fakes, so an
integration can be exercised offline:

    world = syfthub.testing.World()
    hub = syfthub.AsyncHub(options=syfthub.Options(http_client=syfthub.testing.MockTransport(world)))

``world.pay(invoice)`` stands in for the user paying and the provider's webhook; ``world.space_down(path)``
takes a Space offline. The fakes return exactly the shapes the real Hub and Space APIs return."""
from __future__ import annotations

from typing import Any

from .._transport import Response
from .aggregator import FakeAggregator
from .space import FakeHub, FakeSpace, World

__all__ = ["World", "MockTransport", "FakeHub", "FakeSpace", "FakeAggregator"]


class MockTransport:
    """The transport seam, served by the fakes. One per ``World``."""

    def __init__(self, world: World | None = None) -> None:
        self.world = world or World()
        self.hub = FakeHub(self.world)
        self.aggregator = FakeAggregator(self.world)
        self._spaces: dict[str, FakeSpace] = {}

    def space(self, url: str) -> FakeSpace:
        return self._spaces.setdefault(url, FakeSpace(url, self.world))

    # Hub -----------------------------------------------------------------------------------
    async def hub_login(self, method: str, **kw: Any) -> dict[str, Any]:
        return await self.hub.login(method, **kw)

    async def hub_logout(self) -> None:
        await self.hub.logout()

    async def hub_list(self, type_, owner, offset, limit):
        return await self.hub.list(type_, owner, offset, limit)

    async def hub_search(self, text, type_):
        return await self.hub.search(text, type_)

    async def hub_get(self, path):
        return await self.hub.get(path)

    async def hub_collective(self, slug):
        return await self.hub.collective(slug)

    async def hub_token(self, owner, resource, *, guest):
        return await self.hub.satellite_token(owner, resource, guest=guest)

    async def hub_wallet_balance(self) -> float:
        return self.world.hub_wallet

    async def hub_wallet_pay(self, www_authenticate, slug, amount):
        return await self.hub.wallet_pay(www_authenticate, slug, amount)

    # Spaces --------------------------------------------------------------------------------
    async def space_query(self, url, slug, *, token, body, x_payment=None) -> Response:
        return await self.space(url).query(slug, token=token, body=body, x_payment=x_payment)

    async def space_balance(self, url, wallet_id, *, token) -> Response:
        return await self.space(url).balance(wallet_id, token=token)

    async def space_invoice(self, url, wallet_id, *, token, bundle) -> Response:
        return await self.space(url).create_invoice(wallet_id, token=token, bundle_name=bundle)

    # Aggregator ----------------------------------------------------------------------------
    async def aggregate(self, url, payload) -> Response:
        return await self.aggregator.handle(payload)

    # time ----------------------------------------------------------------------------------
    async def sleep(self, seconds: float) -> None:
        await self.world.sleep(seconds)

    def now(self) -> float:
        return self.world.now
