"""Prompt builder for constructing RAG prompts."""

from aggregator.schemas.internal import AggregatedContext
from aggregator.schemas.requests import Message
from aggregator.schemas.responses import Document


class PromptBuilder:
    """Builds prompts for RAG-augmented generation."""

    DEFAULT_SYSTEM_PROMPT = """You are an AI assistant that generates clear summaries with precise source citations.

You will receive multiple documents. Each document includes:
- user_snag/dataset_name
- document_title
- content

Instructions:
1. Write a coherent response to the user's question.
2. Ensure that at least half of the statements are coming from the provided documents.
3. Use inline citations in square brackets using this exact format:
   [<user_snag>/<dataset_name>]
4. If a sentence uses multiple sources, include all citations:
   [SNAG1/DATASET1, SNAG2/DATASET2]
5. Do NOT invent sources or cite anything that is not provided.
6. If the documents do not contain enough information, say so explicitly.
7. At the end of the response, include a "Sources" section listing all cited documents:
   [SNAG/DATASET] <document_title>"""

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
