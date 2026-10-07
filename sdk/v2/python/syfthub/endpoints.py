"""``hub.endpoints``: what the Hub lists, with auto-pagination and local narrowing."""
from __future__ import annotations

from typing import TYPE_CHECKING, AsyncIterator, Iterable

from .errors import NotFound, ValidationError
from .models import Endpoint, EndpointList, EndpointType, Page

if TYPE_CHECKING:  # pragma: no cover
    from .hub import AsyncHub

PAGE_SIZE = 50


class EndpointsNamespace:
    """Find endpoints on the Hub. Reached as ``hub.endpoints``.

    ``list`` and ``search`` return an ``EndpointList`` you can keep narrowing locally and pass straight to
    ``hub.search(sources=...)``."""

    def __init__(self, hub: "AsyncHub") -> None:
        self._hub = hub

    async def list(self, type: EndpointType | str | None = None, *, owner: str | None = None,
                   free: bool | None = None, tag: str | None = None, matching: str | None = None) -> EndpointList:
        """Everything the Hub offers: data sources and models in one table.

        ``type`` and ``owner`` are applied by the Hub; ``free``, ``tag`` and ``matching`` are applied here.
        Pages are followed automatically up to ``Options.max_items``.

        Args:
            type: Keep one kind of endpoint.
            owner: Keep endpoints published by this username.
            free: ``True`` keeps only free endpoints, ``False`` only paid ones.
            tag: Keep endpoints carrying this tag.
            matching: Fuzzy, typo-tolerant text match over name, owner, description, and tags.

        Returns:
            An ``EndpointList``."""
        t = EndpointType(type).value if type is not None else None
        out: list[Endpoint] = []
        async for page in self.pages(t, owner=owner):
            out.extend(page.items)
            if len(out) >= self._hub.options.max_items:
                out = out[: self._hub.options.max_items]
                break
        sel = EndpointList(out).filter(free=free, tag=tag)
        return sel.matching(matching) if matching else sel

    async def pages(self, type: EndpointType | str | None = None, *, owner: str | None = None,
                    page_size: int = PAGE_SIZE) -> AsyncIterator[Page]:
        """The listing one page at a time, for a Hub too large for ``list()``.

        Args:
            type: Keep one kind of endpoint.
            owner: Keep endpoints published by this username.
            page_size: Endpoints per page.

        Yields:
            ``Page`` objects in order."""
        t = EndpointType(type).value if type is not None else None
        offset = 0
        while True:
            items, total = await self._hub._t.hub_list(t, owner, offset, page_size)
            yield Page(items=tuple(items), offset=offset, total=total)
            offset += len(items)
            if not items or offset >= total:
                return

    async def search(self, text: str, *, type: EndpointType | str | None = None) -> EndpointList:
        """Ask the Hub to search its listings semantically. Best first.

        Use this on a large Hub when you do not know what exists yet. If you already have a short list,
        ``(await hub.endpoints.list()).matching(text)`` narrows it without a round trip.

        Args:
            text: What you are looking for, in plain words.
            type: Keep one kind of endpoint.

        Returns:
            An ``EndpointList``."""
        t = EndpointType(type).value if type is not None else None
        return EndpointList(await self._hub._t.hub_search(text, t))

    async def get(self, path: str) -> Endpoint:
        """One endpoint's public record.

        Args:
            path: The endpoint as ``owner/slug``.

        Returns:
            The ``Endpoint``: policies, pricing, how to connect, health, and the fields it filters on.

        Raises:
            ValidationError: When ``path`` is not ``owner/slug``.
            NotFound: When the Hub has no such endpoint."""
        if path.count("/") != 1 or not all(path.split("/")):
            raise ValidationError(f"{path!r} is not an endpoint path; use 'owner/slug'")
        ep = await self._hub._t.hub_get(path)
        if ep is None:
            raise NotFound(f"no endpoint {path!r} on {self._hub.url}", status=404, method="GET",
                           url=f"{self._hub.url}/api/v1/endpoints/{path}")
        return ep

    async def resolve(self, sources: Iterable) -> list[Endpoint]:
        """Turn whatever ``sources=`` accepts into endpoints, each once, in order.

        Args:
            sources: ``Endpoint`` objects, ``owner/slug`` paths, ``collective/name``, or lists of those.

        Returns:
            The endpoints."""
        out: list[Endpoint] = []
        for s in sources:
            if isinstance(s, Endpoint):
                out.append(s)
            elif isinstance(s, str) and s.startswith("collective/"):
                members = await self._hub._t.hub_collective(s.split("/", 1)[1])
                if not members:
                    raise NotFound(f"no collective {s!r}", status=404, method="GET", url=f"{self._hub.url}/api/v1/collectives/{s}")
                for m in members:
                    out.append(await self.get(m))
            elif isinstance(s, str):
                out.append(await self.get(s))
            else:
                out.extend(await self.resolve(s))
        seen, uniq = set(), []
        for e in out:
            if e.path not in seen:
                seen.add(e.path); uniq.append(e)
        return uniq
