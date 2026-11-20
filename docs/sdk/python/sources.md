# Sources

[← Python SDK guide](README.md)

A source is a published endpoint, addressed as `owner/slug`. The catalogue lives on the Hub.

```python
listing = await hub.sources.list()                      # every public source, all pages
mine = await hub.sources.list(owner="erin")             # server-side filters: owner, type, matching
free = await hub.sources.list(free=True, tag="hr")      # local filters: free, tag
hits = await hub.sources.search("parental leave")       # the Hub's keyword search, top_k=10

source = await hub.sources.get("erin/trials")           # SourceNotFound if it does not exist
source.type            # SourceType.DOCUMENTS | MODEL | BOTH
source.pricing         # Pricing | None: rail, price, unit, currency, bundles
source.free            # True when there is no payment policy
source.reachable       # False when the publisher has not connected a Space
source.access(email)   # Access(allowed, rule) from the access policy, predicted client-side
source.metadata_fields # the keys a document's metadata may carry, as the publisher declared them
source.filter_schema   # FilterSchema | None: the fields a query may filter on, with their operators
```

## Listings

`SourceList` is a tuple-like view: `listing.paths`, `listing["erin/trials"]`, `listing[0]`, and
the chainable `filter(type=, owner=, free=, tag=)`, `accessible(viewer)`, `matching(text)` and
`pick(*paths)`. `accessible` takes an email or `hub.me` and keeps the sources whose access policy
admits that viewer, so `listing.filter(free=True).accessible(hub.me)` is what you may search for
nothing. A `SourceList` can be passed straight to `hub.search`.

Every `list`, `get` and `search` call reads the Hub now. `hub.sources.cached(path)` is the only
lookup that does not: it returns what the last read said, for a minute, without a request.

## What a listing says about health

`list` and `search` return what the Hub lists. The Hub delists a source whose Space has stopped
reporting, so a listed source has a live publisher. The SDK exposes no health flag: the Hub's
`health_status` is the Space's own check of the backend behind an endpoint, which the Hub already
acts on, and it says nothing about whether a query will succeed. It stays in `source.raw` if you
want to read it.

## What a source publishes about its answers

`source.metadata_fields` names the keys a returned document's `metadata` may carry, and
`source.filter_schema` names the subset a query may filter on, with each field's type and
operators. Both come from the publisher's Space at publish time. A source with no
`filter_schema` refuses every filter; see [Filtering by metadata](filters.md).
