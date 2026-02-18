"""
Echo model endpoint handler.

This handler echoes back the last user message.
"""


def handler(messages: list, context: dict = None) -> str:
    """
    Echo back the last user message.

    Args:
        messages: List of message dicts with 'role' and 'content' keys
        context: Optional context metadata

    Returns:
        The echoed message
    """
    # Find the last user message
    for msg in reversed(messages):
        if msg.get("role") == "user":
            content = msg.get("content", "")
            return f"Echo: {content}"
    return "No message to echo"
