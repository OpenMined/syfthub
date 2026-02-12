---
slug: sample-docs
type: data_source
name: Sample Documents
description: A sample data source that returns mock documents for demonstration
enabled: true
version: "1.0"
---

# Sample Documents Data Source

This is a simple example data source endpoint that demonstrates the file-based
endpoint configuration. It returns mock documents matching the search query.

## Usage

Send a query string and receive matching documents.

## Example

Request:
```json
{
  "messages": "machine learning"
}
```

Response:
```json
{
  "references": {
    "documents": [
      {
        "document_id": "doc-1",
        "content": "Machine learning is a subset of artificial intelligence...",
        "similarity_score": 0.95
      }
    ]
  }
}
```
