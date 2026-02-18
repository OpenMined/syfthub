---
slug: sample-model
type: model
name: Sample Model
description: A sample model endpoint demonstrating file-based configuration
enabled: true
version: "1.0.0"
env:
  required: []
  optional: [DEBUG]
  inherit: [PATH, HOME]
runtime:
  mode: subprocess
  workers: 1
  timeout: 30
---

# Sample Model Endpoint

This is a sample model endpoint that demonstrates the file-based endpoint
configuration system.

## Usage

Send a POST request to `/api/v1/endpoints/sample-model/query` with:

```json
{
  "messages": [
    {"role": "user", "content": "Hello, how are you?"}
  ]
}
```

## Response

The model will return a friendly response based on the input.
