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

A simple data source endpoint that returns sample documents matching the query. Demonstrates document-level access control and query sanitization.

## Features

- Research group access control with document restrictions
- Strict rate limiting (5 requests/minute)
- SQL injection and path traversal protection

## Usage

```bash
curl -X POST http://localhost:8001/api/v1/endpoints/simple-search/query \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"query": "machine learning"}'
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
