"""Python Expert endpoint handler.

Demonstrates file-based endpoint with environment variable support.
Environment variables are loaded from the .env file in this folder
and accessed via ctx.metadata["env"].
"""

from syfthub_api import Message
from policy_manager.context import RequestContext


async def handler(messages: list[Message], ctx: RequestContext) -> str:
    """
    Python Expert assistant handler.

    Processes user messages and provides Python programming guidance.
    In a real implementation, this would call an LLM API using the
    API key from environment variables.

    Args:
        messages: List of conversation messages
        ctx: Request context with user info, metadata, and env vars

    Returns:
        Expert response as a string
    """
    # Get the last user message
    last_message = None
    for msg in reversed(messages):
        if msg.role == "user":
            last_message = msg.content
            break

    if not last_message:
        return "Hello! I'm your Python Expert. Ask me anything about Python programming, best practices, or code review."

    # Extract user info from context
    user_id = ctx.user_id or "anonymous"

    # Access endpoint-specific environment variables via ctx.metadata["env"]
    # These are loaded from the .env file in this endpoint's folder
    env = ctx.metadata.get("env", {})
    api_key = env.get("OPENAI_API_KEY", "not-configured")
    model_name = env.get("MODEL_NAME", "gpt-4")
    max_tokens = env.get("MAX_TOKENS", "4096")
    debug_mode = env.get("DEBUG_MODE", "false")

    # Mask the API key for display (show first 10 chars only)
    masked_key = api_key[:10] + "..." if len(api_key) > 10 else api_key

    # In production, this would call an LLM API using the env vars
    # For now, return a response demonstrating env var access
    response = f"""🐍 **Python Expert v3.0 - With Environment Variables!**

Hey {user_id}! I received your message:
> {last_message[:150]}{'...' if len(last_message) > 150 else ''}

**Environment Configuration:**
- API Key: `{masked_key}` (masked for security)
- Model: `{model_name}`
- Max Tokens: `{max_tokens}`
- Debug Mode: `{debug_mode}`

This response demonstrates the **file-based endpoint environment variable feature**!
Variables are loaded from `.env` and accessed via `ctx.metadata["env"]`.

🔐 Secrets are isolated per-endpoint, not shared in os.environ.
"""

    return response
