"""Test doubles for apps built on the SDK. No extra dependency: everything runs through
``httpx.MockTransport``.

::

    from syfthub.testing import FakeHub

    fake = FakeHub()
    fake.add_source("alice", "notes")                                   # free document source
    fake.add_source("erin", "trials", price=0.05)                       # prepaid, xendit
    fake.space("erin").reply("trials", documents=[{"content": "16 weeks", "score": 0.8}])
    fake.space("erin").balance = 1.0

    async with fake.hub(budget=1.0) as hub:
        results = await hub.search("leave", ["alice/notes", "erin/trials"]).execute()

``fake.calls`` records every request the SDK sent, redacted, for assertions.
"""

from .fake import FakeHub, FakeSpace, Reply

__all__ = ["FakeHub", "FakeSpace", "Reply"]
