"""
SyftHub Aggregator - RAG orchestration service.

This service coordinates the chat workflow by:
1. Receiving user prompts with model and data source selections
2. Querying data sources for relevant context (in parallel)
3. Building an augmented prompt with retrieved context
4. Calling the model endpoint
5. Streaming/returning the response
"""

__version__ = "0.1.0"
