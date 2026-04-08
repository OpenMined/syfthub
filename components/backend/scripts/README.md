# Backend Scripts

## ingest_existing_endpoints.py

One-time migration script to index all existing public endpoints into Meilisearch.
Run this once after deploying the Meilisearch feature to backfill the search index.

```bash
cd components/backend/
uv run python scripts/ingest_existing_endpoints.py
```

Options:
- `--dry-run` — Show what would be indexed without actually doing it
- `--batch-size N` — Number of endpoints per batch (default: 50)

---

> For seeding the database with test data, see `.claude/skills/syfthub-dev-tools/scripts/`.
