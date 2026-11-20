# Testing your app

[← Python SDK guide](README.md)

`syfthub.testing` ships an in-memory Hub and Spaces over `httpx.MockTransport`, with no extra
dependency, so your tests exercise the real SDK end to end.

```python
from syfthub.testing import FakeHub

fake = FakeHub()
fake.add_source("alice", "notes", description="parental leave policy", metadata_fields=["title"])
fake.add_source("nasa", "news", filters={"fields": {"published": {"type": "datetime", "ops": ["gte"]}}})
fake.add_source("erin", "trials", price=0.05)                 # prepaid, 0.05 USD per request
fake.add_source("kim", "metered", mpp_price=0.02)             # MPP
fake.space("alice").reply("notes", documents=[{"content": "16 weeks", "score": 0.8}])
fake.space("erin").reply("trials", documents=[{"content": "phase 3", "score": 0.7}], cost=0.05)

async with fake.hub(budget=1.0) as hub:
    plan = hub.search("leave", ["alice/notes", "erin/trials"])
    pre = await plan.preflight()                     # erin/trials: NEEDS_CREDITS
    invoice = await pre.actions[0].top_up()
    fake.space("erin").pay(invoice.id)               # simulate the checkout
    results = await plan.execute()

fake.calls                                           # every request, secrets redacted
```

## Scripting what the fake does

- `FakeSpace.reply(slug, documents=..., cost=...)` sets the answer.
- `FakeSpace.reject(slug, outcome="rate_limited", ...)` scripts a refusal.
- A source added with `filters=` refuses a query filter its schema does not allow with the Space's
  own 400, so `Reason.INVALID_FILTER` rows are reachable in tests.
- `FakeHub.users` enforces login; `FakeHub.mpp_error` makes the Hub's pay route fail with a given
  code.
- `fake.space(owner).pay(invoice_id)` settles an invoice.

The sync twin works against the fake too: `syfthub.Hub(fake.url, token="t", options=fake.options())`.
