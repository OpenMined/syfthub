"""
Echo Model - File-based endpoint example.

This handler echoes back the last user message.
"""

from syfthub_api import Message
from policy_manager.context import RequestContext


async def handler(messages: list[Message], ctx: RequestContext) -> str:
    """
    Echo the last user message.

    Args:
        messages: List of conversation messages.
        ctx: Request context with user info and metadata.

    Returns:
        Echo response string.
    """
    # Find the last user message
    last_user_content = ""
    for msg in reversed(messages):
        if msg.role == "user":
            last_user_content = msg.content
            break

    # Get user info from context if available
    user_id = ctx.user_id if ctx else "anonymous"

    return f"Echo from {user_id}: {last_user_content}"
