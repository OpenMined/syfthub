"""Search resource for retrieval-only queries via the Aggregator service.

This is the symmetric counterpart to :class:`~syfthub_sdk.chat.ChatResource`:
where ``client.chat.complete(...)`` retrieves context *and* generates a model
response, ``client.search.query(...)`` retrieves documents from data sources
without invoking any model.

Example usage:
    # Symmetric to client.chat.complete(...)
    response = client.search.query(
        prompt="What happened at EPFL this week?",
        data_sources=["epfl-news/epfl-news"],
    )
    for doc in response.documents:
        print(doc.title, "->", doc.content[:80])

Authentication and billing are handled by the aggregator exactly as for chat:
satellite tokens are minted per data source owner, and metered endpoints that
respond with ``402 Payment Required`` are settled via the user's Hub wallet.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from syfthub_sdk.models import EndpointPublic, EndpointRef, SearchResponse

if TYPE_CHECKING:
    from syfthub_sdk.chat import ChatResource


class SearchResource:
    """Retrieval-only search via the Aggregator.

    Thin facade over :meth:`ChatResource.retrieve`, exposed as ``client.search``
    to mirror the shape of ``client.chat``.
    """

    def __init__(self, chat: ChatResource) -> None:
        """Initialize the search resource.

        Args:
            chat: The chat resource that owns aggregator communication and
                request preparation (satellite tokens, MPP, collective
                expansion). Search reuses it rather than duplicating that logic.
        """
        self._chat = chat

    def query(
        self,
        prompt: str,
        data_sources: list[str | EndpointRef | EndpointPublic] | None = None,
        *,
        top_k: int = 5,
        similarity_threshold: float = 0.5,
        aggregator_url: str | None = None,
        guest_mode: bool = False,
    ) -> SearchResponse:
        """Retrieve documents from data sources without model generation.

        Args:
            prompt: The search query.
            data_sources: Data source endpoints (paths like ``owner/slug``,
                ``EndpointRef``/``EndpointPublic`` objects, or
                ``collective/<slug>`` paths which are expanded to members).
            top_k: Number of documents to retrieve per source (default: 5).
            similarity_threshold: Minimum similarity for retrieved docs
                (default: 0.5).
            aggregator_url: Custom aggregator URL (optional).
            guest_mode: Use guest (unauthenticated) tokens (default: False).

        Returns:
            SearchResponse with retrieved documents and per-source metadata.

        Example:
            response = client.search.query(
                prompt="Hello, world!",
                data_sources=["epfl-news/epfl-news"],
            )
            print(len(response.documents), "documents")
        """
        return self._chat.retrieve(
            prompt=prompt,
            data_sources=data_sources,
            top_k=top_k,
            similarity_threshold=similarity_threshold,
            aggregator_url=aggregator_url,
            guest_mode=guest_mode,
        )
