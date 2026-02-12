"""Prompt builder for constructing RAG prompts."""

from aggregator.schemas.internal import AggregatedContext
from aggregator.schemas.requests import Message
from aggregator.schemas.responses import Document


class PromptBuilder:
    """Builds prompts for RAG-augmented generation."""

    DEFAULT_SYSTEM_PROMPT = """You are a knowledgeable AI assistant that adapts based on available context:

WHEN DOCUMENTS ARE PROVIDED:
Ground your answers in the provided documents. Use reasoning to connect document content to user questions, even when terminology differs. You may make logical inferences from document information, but do not introduce facts that have no basis in the documents.

WHEN NO DOCUMENTS ARE PROVIDED:
Answer helpfully using your general knowledge, like a standard AI assistant."""

    DEFAULT_USER_INSTRUCTIONS = """Your goal is to answer the user's question using information from the provided documents. Use reasoning to connect document content to the question, even when wording differs.

DOCUMENT FORMAT:
Documents appear inside <documents> tags with:
- source: Data source identifier (owner/dataset_name) - use this for citations
- title: Document title
- relevance: Similarity score (0 to 1)
- content: The document text

HOW TO ANSWER:

1. Understand what information would answer the question.

2. Search the documents semantically - look for information that addresses the question even if:
   - Different terminology is used (e.g., "revenue" vs "sales", "employees" vs "headcount")
   - The answer requires connecting multiple pieces of information
   - The information implies the answer rather than stating it verbatim

3. Construct your answer:
   - Draw from document content
   - You MAY make logical inferences clearly supported by the documents
   - Cite every factual claim using: [owner/dataset_name]
   - For multiple sources: [source1, source2]

4. Only if the documents genuinely lack relevant information:
   - Respond: "The provided documents do not contain information to answer this question."

VALID INFERENCE (acceptable):
- Document says "Q3 revenue was $5M, Q4 was $7M" → You can state "Revenue grew 40% from Q3 to Q4" [source]
- Document says "CEO is John Smith" → Answering "Who leads the company?" with "John Smith is CEO" [source]
- Document describes a process → You can summarize or explain it

HALLUCINATION (not acceptable):
- Adding facts not present or implied in documents
- Inventing statistics, dates, names, or details
- Supplementing document info with external knowledge
- Guessing what a document "probably means" without textual support

CITATION FORMAT:
- Every factual claim needs a citation: [owner/dataset_name]
- Uncitable statements should not be included
- Do NOT add a "Sources" section at the end (provided separately by the system)"""

    NO_CONTEXT_INSTRUCTIONS = """No data sources are configured for this query. Answer the question using your general knowledge as a helpful AI assistant.

If the user expected document-grounded answers, they should configure data sources for their query."""

    EMPTY_CONTEXT_INSTRUCTIONS = """The configured data sources did not return any documents for this query.

If the question requires specific information from those data sources, respond:
"The provided documents do not contain information to answer this question."

However, if the question is general and you can provide a helpful answer without needing the specific documents, you may do so while noting that no documents were retrieved."""

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
        """Build the user message content with instructions, context, and question.

        Handles three scenarios:
        1. No context (context is None): General knowledge mode - act as helpful assistant
        2. Empty context (context.documents is empty): Hybrid mode - data sources configured
           but no docs retrieved, can help with general questions
        3. Documents available: Document-grounded mode - answer from documents with citations
        """
        parts: list[str] = []

        # SCENARIO 1: No context provided at all (no data sources configured)
        # → Act as normal helpful assistant using general knowledge
        if context is None:
            parts.append(self.NO_CONTEXT_INSTRUCTIONS)
            parts.append(f"\n---\nUSER QUESTION:\n{user_prompt}\n---")
            return "\n".join(parts)

        # SCENARIO 2: Context provided but empty (data sources configured, no docs retrieved)
        # → Hybrid mode: acknowledge empty results, but can help with general questions
        if not context.documents:
            parts.append(self.EMPTY_CONTEXT_INSTRUCTIONS)
            parts.append(f"\n---\nUSER QUESTION:\n{user_prompt}\n---")
            return "\n".join(parts)

        # SCENARIO 3: Documents available - use document-grounded instructions
        parts.append(self.DEFAULT_USER_INSTRUCTIONS)
        parts.append("\n<documents>")
        parts.append(self._format_context(context))
        parts.append("</documents>")
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
