---
slug: echo-model
type: model
name: Echo Model
description: Echoes back the user message with policy enforcement
enabled: true
version: "1.0.1"
runtime:
  mode: subprocess
  timeout: 30
---

# Echo Model

A simple model endpoint that echoes back the last user message. Demonstrates policy enforcement with access control, rate limiting, and content filtering.

## Features

- Access control via allowed user list
- Rate limiting (10 requests/minute per user)
- Content filtering to block sensitive patterns

## Usage

```bash
curl -X POST http://localhost:8001/api/v1/endpoints/echo-model/query \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"messages": [{"role": "user", "content": "Hello!"}]}'
```

## Response

```json
{
  "summary": {
    "role": "assistant",
    "content": "Echo: Hello!"
  }
}
```
