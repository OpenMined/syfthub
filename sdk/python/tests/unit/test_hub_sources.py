"""hub.sources over respx: pagination, filters, lookup, semantic search, cache."""

from __future__ import annotations

import pytest
import respx

from syfthub import AsyncHub, Options, Retry, SourceNotFound, SourceType

from .conftest import hub_body, xendit_policy

HUB = "https://hub.test"


@pytest.fixture
def api() -> respx.MockRouter:
    with respx.mock(base_url=HUB, assert_all_called=False) as router:
        yield router


@pytest.fixture
async def hub() -> AsyncHub:
    h = AsyncHub(HUB, token="t", options=Options(retry=Retry(attempts=1), max_items=250))
    yield h
    await h.aclose()


def page(n: int, owner: str = "alice", start: int = 0) -> list[dict]:
    return [hub_body(owner, f"src-{i}") for i in range(start, start + n)]


async def test_list_follows_pages_until_a_short_page(api: respx.MockRouter, hub: AsyncHub) -> None:
    route = api.get("/api/v1/endpoints/public").mock(
        side_effect=lambda req: __import__("httpx").Response(
            200,
            json=page(100, start=int(req.url.params["skip"]))
            if int(req.url.params["skip"]) < 100
            else page(7, start=100),
        )
    )
    listing = await hub.sources.list()
    assert len(listing) == 107 and listing.total == 107 and route.call_count == 2
    assert route.calls[0].request.url.params["limit"] == "100"
    assert listing[0].path == "alice/src-0" and listing["alice/src-106"].slug == "src-106"


async def test_list_stops_at_max_items(api: respx.MockRouter, hub: AsyncHub) -> None:
    api.get("/api/v1/endpoints/public").mock(
        side_effect=lambda req: __import__("httpx").Response(
            200, json=page(int(req.url.params["limit"]), start=int(req.url.params["skip"]))
        )
    )
    listing = await hub.sources.list()
    assert len(listing) == 250


async def test_list_filters_go_server_side_where_supported(
    api: respx.MockRouter, hub: AsyncHub
) -> None:
    public = api.get("/api/v1/endpoints/public").respond(
        200, json=[hub_body("alice", "models", type="model")]
    )
    listing = await hub.sources.list(type="model", matching="models")
    assert listing.paths == ("alice/models",)
    params = public.calls.last.request.url.params
    assert params["endpoint_type"] == "model" and params["search"] == "models"

    by_owner = api.get("/api/v1/endpoints/public/by-owner/erin").respond(
        200,
        json=[
            hub_body("erin", "trials", policies=[xendit_policy()], tags=["t"]),
            hub_body("erin", "notes"),
        ],
    )
    erin = await hub.sources.list(owner="erin")
    assert erin.paths == ("erin/trials", "erin/notes") and by_owner.called
    assert (await hub.sources.list(owner="erin", free=True)).paths == ("erin/notes",)
    assert (await hub.sources.list(owner="erin", tag="t")).paths == ("erin/trials",)
    assert (await hub.sources.list(owner="erin", type=SourceType.MODEL)).paths == ()


async def test_get_and_not_found(api: respx.MockRouter, hub: AsyncHub) -> None:
    api.get("/api/v1/endpoints/public/erin/trials").respond(200, json=hub_body("erin", "trials"))
    api.get("/api/v1/endpoints/public/erin/nope").respond(
        404, json={"detail": "Endpoint not found"}
    )
    src = await hub.sources.get("erin/trials")
    assert src.path == "erin/trials" and src.health.value == "healthy"
    with pytest.raises(SourceNotFound) as e:
        await hub.sources.get("erin/nope")
    assert e.value.path == "erin/nope"


async def test_get_always_reads_and_cached_is_a_sync_lookup(
    api: respx.MockRouter, hub: AsyncHub
) -> None:
    route = api.get("/api/v1/endpoints/public/erin/trials").respond(
        200, json=hub_body("erin", "trials")
    )
    a = await hub.sources.get("erin/trials")
    b = await hub.sources.get("erin/trials")
    assert a == b and route.call_count == 2  # every get is a read
    assert hub.sources.cached("erin/trials") == a  # what the last read said, no request
    hub.sources.forget("erin/trials")
    assert hub.sources.cached("erin/trials") is None
    resolved = await hub.sources.resolve(("erin/trials",))
    assert resolved["erin/trials"].slug == "trials" and route.call_count == 3


async def test_semantic_search(api: respx.MockRouter, hub: AsyncHub) -> None:
    route = api.post("/api/v1/endpoints/search").respond(
        200,
        json={
            "results": [{**hub_body("erin", "trials"), "relevance_score": 0.9}],
            "total": 1,
            "query": "trials",
        },
    )
    found = await hub.sources.search("clinical trials", top_k=3)
    assert found.paths == ("erin/trials",) and found.total == 1
    assert route.calls.last.request.content == b'{"query":"clinical trials","top_k":3}'
