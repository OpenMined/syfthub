"""Prompt builder for constructing RAG prompts."""

from aggregator.schemas.internal import AggregatedContext
from aggregator.schemas.requests import Message
from aggregator.schemas.responses import Document


class PromptBuilder:
    """Builds prompts for RAG-augmented generation."""

    DEFAULT_SYSTEM_PROMPT = """You are a document-grounded AI assistant. You ONLY provide answers based on information explicitly stated in the provided documents. You never use your training knowledge or make assumptions beyond what the documents contain."""

    DEFAULT_USER_INSTRUCTIONS = """CRITICAL RULES - YOU MUST FOLLOW THESE:
1. Your answer must be drawn EXCLUSIVELY from the documents provided below.
2. You must NEVER use your training data or general knowledge to answer questions.
3. If the documents do not contain information relevant to the question, you MUST respond:
   "The provided documents do not contain information to answer this question."
   DO NOT attempt to answer from your own knowledge.

DOCUMENT FORMAT:
You will receive documents inside <documents> tags. Each document includes:
- source: The data source identifier (owner/dataset_name)
- title: Document title
- relevance: Similarity score (0 to 1)
- content: The document text

RESPONSE PROCESS:
1. Search the provided documents for information relevant to the user's question.
2. If relevant information is found:
   - Answer using ONLY that information
   - Cite EVERY factual statement using the format: [owner/dataset_name]
   - Multiple sources for one statement: [source1, source2]
3. If NO relevant information is found:
   - State clearly: "The provided documents do not contain information to answer this question."
   - DO NOT guess, speculate, or use external knowledge.

CITATION REQUIREMENTS:
- EVERY factual claim must have a citation from the provided documents.
- Use this exact format: [owner/dataset_name]
- If you cannot cite a statement from the documents, do not include that statement.
- Do NOT include a "Sources" section at the end - sources are provided separately by the system.

EXAMPLE OF CORRECT BEHAVIOR:
Question: "What is the company's revenue?"
Documents contain revenue data → "The company's revenue was $10M in 2024 [acme/financial-reports]."
Documents do NOT contain revenue → "The provided documents do not contain information to answer this question."

EXAMPLE OF INCORRECT BEHAVIOR (DO NOT DO THIS):
Question: "What is the company's revenue?"
Documents do NOT contain revenue → Making up "$5M" or using general knowledge about typical revenues.

Remember: If you cannot find the answer in the provided documents, say so. Never invent information."""

    def __init__(self, system_prompt: str | None = None):
        self.system_prompt = system_prompt or self.DEFAULT_SYSTEM_PROMPT

    def build(
        self,
        user_prompt: str,
        context: AggregatedContext | None = None,
        custom_system_prompt: str | None = None,
        history: list[Message] | None = None,
    ) -> list[Message]:
        """
        Build a list of messages for the model, incorporating retrieved context.

        Args:
            user_prompt: The user's original question/prompt
            context: Aggregated context from data sources (optional)
            custom_system_prompt: Override the default system prompt
            history: Prior conversation turns for multi-turn context

        Returns:
            List of messages ready to send to the model.
            Format: [system, *history, user_with_RAG_context]
        """
        messages: list[Message] = []

        # Build simple system message
        system_content = custom_system_prompt or self.system_prompt
        messages.append(Message(role="system", content=system_content))

        # Insert conversation history between system and new user message
        if history:
            for msg in history:
                messages.append(Message(role=msg.role, content=msg.content))

        # Build user message with instructions, context, and question blended
        user_content = self._build_user_content(
            user_prompt=user_prompt,
            context=context,
        )
        messages.append(Message(role="user", content=user_content))

        return messages

    def _build_user_content(
        self,
        user_prompt: str,
        context: AggregatedContext | None,
    ) -> str:
        """Build the user message content with instructions, context, and question."""
        parts: list[str] = []

        # Add instructions
        parts.append(self.DEFAULT_USER_INSTRUCTIONS)

        # Add context if available - using XML tags for clear structure
        if context and context.documents:
            parts.append("\n<documents>")
            parts.append(self._format_context(context))
            parts.append("</documents>")
        elif context and not context.documents:
            # No documents retrieved - instruct model to refuse answering
            parts.append(
                "\n<documents>\nNo relevant documents were retrieved from the selected data sources.\n</documents>\n"
                "IMPORTANT: Since no relevant documents were found, you MUST respond with:\n"
                '"The provided documents do not contain information to answer this question."\n'
                "Do NOT attempt to answer using your own knowledge."
            )
        else:
            # No context provided at all
            parts.append(
                "\n<documents>\nNo documents were provided.\n</documents>\n"
                "IMPORTANT: Since no documents were provided, you MUST respond with:\n"
                '"No documents were provided to answer this question."\n'
                "Do NOT attempt to answer using your own knowledge."
            )

        # Add user question
        parts.append(f"\n---\nUSER QUESTION:\n{user_prompt}\n---")

        return "\n".join(parts)

    def _format_context(self, context: AggregatedContext) -> str:
        """Format retrieved documents as context using XML structure.

        Formats documents with clear XML tags for better model parsing:
        - source: owner/endpoint-slug (for citations)
        - title: from metadata or fallback
        - relevance: similarity score (0-1)
        - content: document text
        """
        formatted_parts: list[str] = []
        doc_number = 1

        # Group documents by source
        docs_by_source: dict[str, list[Document]] = {}
        for result in context.retrieval_results:
            if result.status == "success" and result.documents:
                docs_by_source[result.endpoint_path] = result.documents

        # Format each source's documents with XML tags
        for source_path, documents in docs_by_source.items():
            for doc in documents:
                # Extract title from metadata or use fallback
                title = (
                    doc.metadata.get("title")
                    or doc.metadata.get("document_title")
                    or f"Document {doc_number}"
                )
                relevance = f"{doc.score:.2f}" if doc.score > 0 else "N/A"

                formatted_parts.append(f"""
<document index="{doc_number}">
<source>{source_path}</source>
<title>{title}</title>
<relevance>{relevance}</relevance>
<content>
{doc.content}
</content>
</document>""")
                doc_number += 1

        # If no grouped documents, fall back to flat list
        if not formatted_parts and context.documents:
            for doc in context.documents:
                title = (
                    doc.metadata.get("title")
                    or doc.metadata.get("document_title")
                    or f"Document {doc_number}"
                )
                relevance = f"{doc.score:.2f}" if doc.score > 0 else "N/A"

                formatted_parts.append(f"""
<document index="{doc_number}">
<source>unknown</source>
<title>{title}</title>
<relevance>{relevance}</relevance>
<content>
{doc.content}
</content>
</document>""")
                doc_number += 1

        return "\n".join(formatted_parts)
