"""
Sample model endpoint handler.

This handler receives messages and returns a response.
The handler function must be named 'handler' and accept:
- messages: list[dict] - The conversation messages
- context: dict - Request context metadata (optional)
"""

import os


def handler(messages: list[dict], context: dict = None) -> str:
    """
    Handle a model query request.

    Args:
        messages: List of message dicts with 'role' and 'content' keys
        context: Optional context metadata from the request

    Returns:
        The assistant's response as a string
    """
    # Get debug mode from environment
    debug = os.environ.get("DEBUG", "false").lower() == "true"

    if debug:
        print(f"Received {len(messages)} messages")
        if context:
            print(f"Context: {context}")

    # Find the last user message
    last_user_message = None
    for msg in reversed(messages):
        if msg.get("role") == "user":
            last_user_message = msg.get("content", "")
            break

    if not last_user_message:
        return "I didn't receive any message from you. How can I help?"

    # Generate a simple response
    response = f"Hello! You said: '{last_user_message}'. This is a sample response from the file-based model endpoint."

    if debug:
        print(f"Response: {response}")

    return response


# Support for async handlers (optional)
async def async_handler(messages: list[dict], context: dict = None) -> str:
    """Async version of the handler."""
    return handler(messages, context)
