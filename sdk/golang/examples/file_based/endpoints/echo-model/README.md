---
slug: echo-model
type: model
name: Echos Model
description: Echos back the user message
enabled: true
version: "1.0.1"
runtime:
  mode: subprocess
  timeout: 30
---

# Echo Model

A simple model endpoint that echoes back the last user message.

## Usage

```bash
curl -X POST http://localhost:8001/api/v1/endpoints/echo-model/query \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer test-token" \
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
