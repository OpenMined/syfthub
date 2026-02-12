---
slug: echo-model
type: model
name: Echo Model
description: A simple model that echoes back the last user message
enabled: true
version: "1.0"
---

# Echo Model

This is a simple example model endpoint that demonstrates the file-based
endpoint configuration. It echoes back the last user message with a prefix.

## Usage

Send a message to this endpoint and it will respond with an echo.

## Example

Request:
```json
{
  "messages": [
    {"role": "user", "content": "Hello, world!"}
  ]
}
```

Response:
```json
{
  "summary": {
    "message": {
      "role": "assistant",
      "content": "Echo: Hello, world!"
    }
  }
}
```
