---
slug: simple-search
type: data_source
name: Simple Search
description: A simple search endpoint that returns sample documents
enabled: true
version: "1.0.0"
runtime:
  mode: subprocess
  timeout: 30
---

# Simple Search

A simple data source endpoint that returns sample documents matching the query.

## Usage

```bash
curl -X POST http://localhost:8001/api/v1/endpoints/simple-search/query \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer test-token" \
  -d '{"messages": [{"role": "user", "content": "machine learning"}]}'
```

## Response

```json
{
  "references": [
    {
      "document_id": "doc-1",
      "content": "...",
      "similarity_score": 0.95
    }
  ]
}
```
