"""Prompt builder for constructing RAG prompts."""

from aggregator.schemas.internal import AggregatedContext
from aggregator.schemas.requests import Message
from aggregator.schemas.responses import Document


class PromptBuilder:
    """Builds prompts for RAG-augmented generation."""

    DEFAULT_SYSTEM_PROMPT = """You are a helpful assistant that answers questions based on the provided context.

When answering:
- Use the context information below to inform your response
- If the context doesn't contain relevant information, acknowledge this
- Cite sources when directly using information from the context
- Be concise but comprehensive
- If you're unsure, say so rather than making up information"""

    def __init__(self, system_prompt: str | None = None):
        self.system_prompt = system_prompt or self.DEFAULT_SYSTEM_PROMPT

    def build(
        self,
        user_prompt: str,
        context: AggregatedContext | None = None,
        custom_system_prompt: str | None = None,
    ) -> list[Message]:
        """
        Build a list of messages for the model, incorporating retrieved context.

        Args:
            user_prompt: The user's original question/prompt
            context: Aggregated context from data sources (optional)
            custom_system_prompt: Override the default system prompt

        Returns:
            List of messages ready to send to the model
        """
        messages: list[Message] = []

        # Build system message with context
        system_content = self._build_system_content(
            context=context,
            custom_system_prompt=custom_system_prompt,
        )
        messages.append(Message(role="system", content=system_content))

        # Add user message
        messages.append(Message(role="user", content=user_prompt))

        return messages

    def _build_system_content(
        self,
        context: AggregatedContext | None,
        custom_system_prompt: str | None,
    ) -> str:
        """Build the system message content with context."""
        parts: list[str] = []

        # Add system prompt
        system_prompt = custom_system_prompt or self.system_prompt
        parts.append(system_prompt)

        # Add context if available
        if context and context.documents:
            parts.append("\n---\nCONTEXT FROM DATA SOURCES:\n")
            parts.append(self._format_context(context))
            parts.append("\n---")
        elif context and not context.documents:
            parts.append(
                "\n---\nNote: No relevant context was found in the selected data sources. "
                "Please answer based on your general knowledge.\n---"
            )

        return "\n".join(parts)

    def _format_context(self, context: AggregatedContext) -> str:
        """Format retrieved documents as context."""
        formatted_parts: list[str] = []

        # Group documents by source
        docs_by_source: dict[str, list[Document]] = {}
        for result in context.retrieval_results:
            if result.status == "success" and result.documents:
                docs_by_source[result.endpoint_path] = result.documents

        # Format each source's documents
        for source_path, documents in docs_by_source.items():
            formatted_parts.append(f"\n### Source: {source_path}")

            for i, doc in enumerate(documents, 1):
                score_info = f" [Relevance: {doc.score:.2f}]" if doc.score > 0 else ""
                formatted_parts.append(f"\n[Document {i}]{score_info}")
                formatted_parts.append(doc.content)

        # If no grouped documents, fall back to flat list
        if not formatted_parts and context.documents:
            for i, doc in enumerate(context.documents, 1):
                score_info = f" [Relevance: {doc.score:.2f}]" if doc.score > 0 else ""
                formatted_parts.append(f"\n[Document {i}]{score_info}")
                formatted_parts.append(doc.content)

        return "\n".join(formatted_parts)
