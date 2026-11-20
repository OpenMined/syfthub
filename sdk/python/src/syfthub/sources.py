"""``hub.sources``: list, get and search Hub endpoints as sources, with a short per-session cache."""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING, Any

from .models.enums import SourceType
from .models.search import as_path
from .models.sources import Source, SourceList

if TYPE_CHECKING:
    from ._api.hub import HubApi

_PAGE = 100
_CACHE_TTL = 60.0


class SourcesNamespace:
    """``hub.sources``: the Hub's public endpoints as ``Source`` objects.

    ``list`` and ``search`` are catalogue reads; ``get`` and ``resolve`` read one source each,
    fresh. ``cached`` is the only lookup that answers without a request.
    """

    def __init__(self, api: HubApi, *, max_items: int = 1000, concurrency: int = 8) -> None:
        """``hub.sources``.

        Args:
            api: the Hub API.
            max_items: the most sources ``list`` reads.
            concurrency: parallel reads in ``resolve``.
        """
        self._api = api
        self._max_items = max_items
        self._concurrency = concurrency
        self._cache: dict[str, tuple[float, Source]] = {}

    # ── remote ────────────────────────────────────────────────────────────

    async def list(
        self,
        *,
        owner: str | None = None,
        type: SourceType | str | None = None,
        free: bool | None = None,
        tag: str | None = None,
        matching: str | None = None,
    ) -> SourceList:
        """All pages up to ``Options.max_items``.

        ``owner``, ``type`` and ``matching`` are server-side filters where the Hub supports
        them; ``free`` and ``tag`` are local.

        Args:
            owner: only this publisher's sources.
            type: only this source type.
            free: only free (True) or only paid (False) sources.
            tag: only sources carrying this tag.
            matching: the Hub's keyword match.

        Returns:
            The matching sources, with the Hub's total before local filters.
        """
        want_type = SourceType(type) if isinstance(type, str) else type
        bodies: list[dict[str, Any]] = []
        skip = 0
        while len(bodies) < self._max_items:
            limit = min(_PAGE, self._max_items - len(bodies))
            if owner is not None:
                page = await self._api.list_by_owner(owner, skip=skip, limit=limit)
            else:
                page = await self._api.list_public(
                    skip=skip,
                    limit=limit,
                    endpoint_type=want_type.value if want_type else None,
                    search=matching,
                )
            bodies.extend(page)
            if len(page) < limit:
                break
            skip += len(page)
        sources = [self._remember(Source.from_hub(b)) for b in bodies]
        listing = SourceList(items=tuple(sources), total=len(sources))
        if owner is not None and (want_type is not None or matching):
            listing = listing.filter(type=want_type)
            if matching:
                listing = listing.matching(matching)
        if free is not None or tag is not None:
            listing = listing.filter(free=free, tag=tag)
        return listing

    async def get(self, path: str | Source) -> Source:
        """One source by ``owner/slug``, read from the Hub now. Raises ``SourceNotFound``.

        Args:
            path: ``owner/slug``.

        Returns:
            The source as the Hub lists it now.
        """
        key = as_path(path)
        owner, slug = key.split("/", 1)
        body = await self._api.get_public(owner, slug)
        return self._remember(Source.from_hub(body))

    async def search(self, text: str, *, top_k: int = 10) -> SourceList:
        """The Hub's keyword search over the listing, best first.

        ``POST /endpoints/search``: a full-text match on name, description, readme and tags.

        Args:
            text: the words to match.
            top_k: how many to return.

        Returns:
            The best matches, best first.
        """
        body = await self._api.search(text, top_k=top_k)
        results = body.get("results") or []
        sources = [self._remember(Source.from_hub(r)) for r in results if isinstance(r, dict)]
        return SourceList(items=tuple(sources), total=int(body.get("total") or len(sources)))

    async def resolve(self, paths: tuple[str, ...]) -> dict[str, Source]:
        """Sources for ``paths``, each read from the Hub now.

        Args:
            paths: ``owner/slug`` strings.

        Returns:
            ``path -> Source`` for every path.

        Raises:
            SourceNotFound: for a path the Hub does not list.
        """
        gate = asyncio.Semaphore(self._concurrency)

        async def one(path: str) -> Source:
            async with gate:
                return await self.get(path)

        sources = await asyncio.gather(*(one(p) for p in paths))
        return dict(zip(paths, sources, strict=True))

    # ── cache: a one-minute memory of what the Hub said, for sync lookups only ──

    def _remember(self, source: Source) -> Source:
        self._cache[source.path] = (time.monotonic() + _CACHE_TTL, source)
        return source

    def cached(self, path: str) -> Source | None:
        """The source as last read this session, if read within the last minute; no request.

        Args:
            path: ``owner/slug``.

        Returns:
            The cached source, or None when unread or stale.
        """
        hit = self._cache.get(path)
        return hit[1] if hit and hit[0] > time.monotonic() else None

    def forget(self, path: str | None = None) -> None:
        """Drop the cached ``Source`` for ``path``, or every one, so the next read hits the Hub.

        Args:
            path: ``owner/slug``, or None for every cached source.
        """
        if path is None:
            self._cache.clear()
        else:
            self._cache.pop(path, None)
