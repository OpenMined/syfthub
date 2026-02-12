---
slug: python-expert
type: model
name: Python Expert
description: An AI assistant specialized in Python programming, best practices, and code review.
enabled: true
version: "1.0.0"
env:
  required:
    - OPENAI_API_KEY
  optional:
    - MODEL_NAME
    - MAX_TOKENS
    - DEBUG_MODE
runtime:
  mode: in_process  # Options: in_process, subprocess, container
  workers: 2        # Number of worker processes (for subprocess mode)
  timeout: 30       # Execution timeout in seconds
  extras: []        # Optional dependency extras from pyproject.toml
---

# Python Expert

An AI-powered Python programming assistant that helps with:

- Code review and best practices
- Debugging and error analysis
- Performance optimization suggestions
- Pythonic code patterns
- Library recommendations

## Usage

Send a message with your Python question or code snippet, and the expert will provide guidance.

## Rate Limits

- 100 requests per minute per user
- 10000 tokens per request
