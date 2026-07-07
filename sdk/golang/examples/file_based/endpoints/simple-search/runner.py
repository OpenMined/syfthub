"""
Simple search data source endpoint handler.

This handler returns sample documents based on the query.
"""

# Sample documents database
DOCUMENTS = [
    {
        "document_id": "doc-001",
        "content": "Machine learning is a subset of artificial intelligence that enables systems to learn from data.",
        "metadata": {"title": "ML Basics", "category": "ai"},
    },
    {
        "document_id": "doc-002",
        "content": "Deep learning uses neural networks with multiple layers to process complex patterns.",
        "metadata": {"title": "Deep Learning", "category": "ai"},
    },
    {
        "document_id": "doc-003",
        "content": "Python is a popular programming language for data science and machine learning.",
        "metadata": {"title": "Python for ML", "category": "programming"},
    },
    {
        "document_id": "doc-004",
        "content": "Natural language processing enables computers to understand human language.",
        "metadata": {"title": "NLP Overview", "category": "ai"},
    },
]


def handler(query: str, context: dict = None) -> list:
    """
    Search for documents matching the query.

    Args:
        query: The search query string
        context: Optional context metadata

    Returns:
        List of matching documents with similarity scores
    """
    query_lower = query.lower()
    results = []

    for doc in DOCUMENTS:
        content_lower = doc["content"].lower()
        title_lower = doc["metadata"]["title"].lower()

        # Simple keyword matching (in real implementation, use embeddings)
        score = 0.0

        # Check for query terms in content
        query_terms = query_lower.split()
        for term in query_terms:
            if term in content_lower:
                score += 0.3
            if term in title_lower:
                score += 0.2

        # Cap score at 1.0
        score = min(score, 1.0)

        if score > 0:
            results.append({
                "document_id": doc["document_id"],
                "content": doc["content"],
                "metadata": doc["metadata"],
                "similarity_score": round(score, 2),
            })

    # Sort by score descending
    results.sort(key=lambda x: x["similarity_score"], reverse=True)

    # Return top 5 results
    return results[:5]
