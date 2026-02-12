"""
Sample Documents - File-based data source endpoint example.

This handler returns mock documents matching the search query.
"""

from syfthub_api import Document, Message
from policy_manager.context import RequestContext


# Mock document database
MOCK_DOCUMENTS = [
    {
        "id": "doc-ml-101",
        "content": "Machine learning is a subset of artificial intelligence that enables "
        "systems to learn and improve from experience without being explicitly programmed.",
        "keywords": ["machine learning", "ai", "artificial intelligence"],
    },
    {
        "id": "doc-dl-201",
        "content": "Deep learning is a type of machine learning that uses neural networks "
        "with multiple layers to progressively extract higher-level features from raw input.",
        "keywords": ["deep learning", "neural networks", "machine learning"],
    },
    {
        "id": "doc-nlp-301",
        "content": "Natural language processing (NLP) is a branch of AI that helps computers "
        "understand, interpret, and manipulate human language.",
        "keywords": ["nlp", "natural language processing", "language", "ai"],
    },
    {
        "id": "doc-cv-401",
        "content": "Computer vision is a field of AI that trains computers to interpret "
        "and understand the visual world using digital images and deep learning models.",
        "keywords": ["computer vision", "image", "visual", "ai"],
    },
]


async def handler(messages: list[Message], ctx: RequestContext) -> list[Document]:
    """
    Search for documents matching the query.

    The query is extracted from the messages (the user's search query).

    Args:
        messages: List containing the search query as the user message.
        ctx: Request context with user info and metadata.

    Returns:
        List of matching Document objects.
    """
    # Extract query from messages (first user message content)
    query = ""
    for msg in messages:
        if msg.role == "user":
            query = msg.content.lower()
            break

    if not query:
        return []

    # Simple keyword matching
    results = []
    for doc in MOCK_DOCUMENTS:
        # Check if query matches any keywords or is in content
        score = 0.0
        for keyword in doc["keywords"]:
            if keyword in query or query in keyword:
                score = max(score, 0.9)
        if query in doc["content"].lower():
            score = max(score, 0.7)

        if score > 0:
            results.append(
                Document(
                    document_id=doc["id"],
                    content=doc["content"],
                    similarity_score=score,
                    metadata={"keywords": doc["keywords"]},
                )
            )

    # Sort by score and return top results
    results.sort(key=lambda d: d.similarity_score, reverse=True)
    return results[:5]
