"""Against a running Hub and Space. Skipped unless ``SYFTHUB_URL`` and ``SYFTHUB_TOKEN`` are set.

Optional: ``SYFTHUB_TEST_SOURCE`` (``owner/slug``) names a free, published source to query.
"""

from __future__ import annotations

import os

import pytest

from syfthub import AsyncHub, Hub, Outcome

pytestmark = pytest.mark.integration

URL = os.environ.get("SYFTHUB_URL")
TOKEN = os.environ.get("SYFTHUB_TOKEN")
SOURCE = os.environ.get("SYFTHUB_TEST_SOURCE")

needs_hub = pytest.mark.skipif(not (URL and TOKEN), reason="SYFTHUB_URL and SYFTHUB_TOKEN unset")
needs_source = pytest.mark.skipif(not SOURCE, reason="SYFTHUB_TEST_SOURCE unset")


@needs_hub
async def test_identity_and_catalogue() -> None:
    async with AsyncHub(URL, token=TOKEN) as hub:
        me = await hub.auth.whoami()
        assert me.username
        listing = await hub.sources.list()
        assert listing.total >= 0
        for source in listing:
            assert source.path and source.type


@needs_hub
@needs_source
async def test_search_one_source() -> None:
    assert SOURCE is not None
    async with AsyncHub(URL, token=TOKEN) as hub:
        plan = hub.search("what is this about?", [SOURCE], limit=3)
        pre = await plan.preflight()
        assert SOURCE in [r.path for r in pre]
        results = await plan.execute()
        row = results[SOURCE]
        assert row.outcome in (Outcome.RETURNED, Outcome.REJECTED, Outcome.HELD, Outcome.FAILED)
        if row.ok:
            assert row.status_code == 200


@needs_hub
def test_sync_twin_against_the_live_hub() -> None:
    with Hub(URL, token=TOKEN) as hub:
        assert hub.auth.whoami().username
        assert len(hub.sources.list()) >= 0
