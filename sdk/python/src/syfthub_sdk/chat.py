"""Chat resource for RAG-augmented conversations via the Aggregator service.

This module provides high-level chat functionality that integrates with the
SyftHub Aggregator service for RAG (Retrieval-Augmented Generation) workflows.

This resource handles satellite token authentication automatically:
- Resolves endpoints and extracts owner information
- Exchanges Hub access tokens for satellite tokens (one per unique owner)
- Sends tokens to the aggregator for forwarding to SyftAI-Space

Example usage:
    # Simple chat completion
    response = client.chat.complete(
        prompt="What are the key features?",
        model="alice/gpt-model",
        data_sources=["bob/docs-dataset"],
    )
    print(response.response)

    # Streaming chat
    for event in client.chat.stream(
        prompt="Explain machine learning",
        model="alice/gpt-model",
    ):
        if event.type == "token":
            print(event.content, end="")

    # Get available models and data sources
    models = list(client.chat.get_available_models())
    sources = list(client.chat.get_available_data_sources())
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal

import httpx

from syfthub_sdk.exceptions import (
    AggregatorError,
    EndpointResolutionError,
)
from syfthub_sdk.models import (
    ChatMetadata,
    ChatResponse,
    DocumentSource,
    EndpointPublic,
    EndpointRef,
    EndpointType,
    SourceInfo,
    SourceStatus,
    TokenUsage,
)

if TYPE_CHECKING:
    from syfthub_sdk.auth import AuthResource
    from syfthub_sdk.hub import HubResource

logger = logging.getLogger(__name__)


# =============================================================================
# Streaming Event Types
# =============================================================================


@dataclass(frozen=True)
class RetrievalStartEvent:
    """Fired when retrieval begins."""

    type: Literal["retrieval_start"] = field(default="retrieval_start", repr=False)
    source_count: int = 0


@dataclass(frozen=True)
class SourceCompleteEvent:
    """Fired when a single source finishes querying."""

    type: Literal["source_complete"] = field(default="source_complete", repr=False)
    path: str = ""
    status: str = ""
    documents_retrieved: int = 0


@dataclass(frozen=True)
class RetrievalCompleteEvent:
    """Fired when all retrieval is done."""

    type: Literal["retrieval_complete"] = field(
        default="retrieval_complete", repr=False
    )
    total_documents: int = 0
    time_ms: int = 0


@dataclass(frozen=True)
class RerankingStartEvent:
    """Fired when document reranking begins (after all sources complete)."""

    type: Literal["reranking_start"] = field(default="reranking_start", repr=False)
    documents: int = 0


@dataclass(frozen=True)
class RerankingCompleteEvent:
    """Fired when document reranking completes."""

    type: Literal["reranking_complete"] = field(
        default="reranking_complete", repr=False
    )
    documents: int = 0
    time_ms: int = 0


@dataclass(frozen=True)
class GenerationStartEvent:
    """Fired when model generation begins."""

    type: Literal["generation_start"] = field(default="generation_start", repr=False)


@dataclass(frozen=True)
class GenerationHeartbeatEvent:
    """Fired periodically during non-streaming model generation (~every 3s)."""

    type: Literal["generation_heartbeat"] = field(
        default="generation_heartbeat", repr=False
    )
    elapsed_ms: int = 0


@dataclass(frozen=True)
class TokenEvent:
    """Fired for each token from the model."""

    type: Literal["token"] = field(default="token", repr=False)
    content: str = ""


@dataclass(frozen=True)
class DoneEvent:
    """Fired when generation completes successfully."""

    type: Literal["done"] = field(default="done", repr=False)
    sources: dict[str, DocumentSource] = field(default_factory=dict)
    retrieval_info: list[SourceInfo] = field(default_factory=list)
    metadata: ChatMetadata | None = None
    usage: TokenUsage | None = (
        None  # Token usage if available (only from non-streaming)
    )


@dataclass(frozen=True)
class ErrorEvent:
    """Fired on error."""

    type: Literal["error"] = field(default="error", repr=False)
    message: str = ""


ChatStreamEvent = (
    RetrievalStartEvent
    | SourceCompleteEvent
    | RetrievalCompleteEvent
    | RerankingStartEvent
    | RerankingCompleteEvent
    | GenerationStartEvent
    | GenerationHeartbeatEvent
    | TokenEvent
    | DoneEvent
    | ErrorEvent
)


# =============================================================================
# Chat Resource
# =============================================================================


TUNNELING_PREFIX = "tunneling:"


class ChatResource:
    """Chat resource for RAG-augmented conversations via the Aggregator.

    This resource provides high-level chat functionality that:
    - Queries data sources for relevant context (retrieval)
    - Sends prompts with context to model endpoints (generation)
    - Supports both synchronous and streaming responses

    The resource handles satellite token authentication automatically:
    - Resolves endpoints and extracts owner information
    - Exchanges Hub access tokens for satellite tokens (one per unique owner)
    - Sends tokens to the aggregator for forwarding to SyftAI-Space

    The aggregator service handles the RAG orchestration, including:
    - Parallel querying of multiple data sources
    - Context aggregation and prompt building
    - Model generation with streaming support

    Example:
        # Complete a chat request
        response = client.chat.complete(
            prompt="What are the key features of Python?",
            model="alice/gpt-4-endpoint",
            data_sources=["bob/python-docs", "carol/tutorials"],
        )
        print(response.response)
        print(f"Completed in {response.metadata.total_time_ms}ms")

        # Stream a chat response
        for event in client.chat.stream(
            prompt="Explain neural networks",
            model="alice/gpt-4-endpoint",
        ):
            if event.type == "token":
                print(event.content, end="", flush=True)
            elif event.type == "done":
                print(f"\\nSources: {[s.path for s in event.sources]}")
    """

    def __init__(
        self,
        hub: HubResource,
        auth: AuthResource,
        aggregator_url: str,
    ) -> None:
        """Initialize chat resource.

        Args:
            hub: Hub resource for endpoint lookups
            auth: Auth resource for satellite token exchange
            aggregator_url: Base URL of the aggregator service
        """
        self._hub = hub
        self._auth = auth
        self._aggregator_url = aggregator_url.rstrip("/")
        # Separate client for aggregator with longer timeout (LLM can be slow)
        self._agg_client = httpx.Client(timeout=120.0)

    @staticmethod
    def _type_matches(actual_type: str, expected_type: str) -> bool:
        """Check if an endpoint type matches the expected type.

        A model_data_source endpoint matches both 'model' and 'data_source'.
        """
        if actual_type == expected_type:
            return True
        if actual_type == EndpointType.MODEL_DATA_SOURCE.value:
            return expected_type in (
                EndpointType.MODEL.value,
                EndpointType.DATA_SOURCE.value,
            )
        return False

    def _resolve_endpoint_ref(
        self,
        endpoint: str | EndpointRef | EndpointPublic,
        expected_type: str | None = None,
    ) -> EndpointRef:
        """Convert any endpoint format to EndpointRef with URL and owner info.

        The owner_username is critical for satellite token authentication.

        Args:
            endpoint: Endpoint path, EndpointRef, or EndpointPublic
            expected_type: Expected endpoint type ("model" or "data_source")

        Returns:
            EndpointRef with URL, slug, and owner_username

        Raises:
            EndpointResolutionError: If endpoint cannot be resolved
            ValueError: If endpoint type doesn't match expected
        """
        if isinstance(endpoint, EndpointRef):
            return endpoint

        if isinstance(endpoint, EndpointPublic):
            # Validate type if expected (model_data_source matches both model and data_source)
            if expected_type and not self._type_matches(
                endpoint.type.value, expected_type
            ):
                raise ValueError(
                    f"Expected endpoint type '{expected_type}', "
                    f"got '{endpoint.type.value}' for '{endpoint.slug}'"
                )

            # Find first enabled connection with URL
            for conn in endpoint.connect:
                if conn.enabled and conn.config.get("url"):
                    return EndpointRef(
                        url=str(conn.config["url"]),
                        slug=endpoint.slug,
                        name=endpoint.name,
                        tenant_name=conn.config.get("tenant_name"),
                        owner_username=endpoint.owner_username,  # Capture owner for satellite token
                    )

            raise EndpointResolutionError(
                f"Endpoint '{endpoint.slug}' has no connection with URL configured. "
                "Please ensure the endpoint has a connection with 'url' in its config.",
                endpoint_path=f"{endpoint.owner_username}/{endpoint.slug}",
            )

        if isinstance(endpoint, str):
            # Path format "owner/slug" - fetch from hub
            try:
                ep = self._hub.get(endpoint)
            except Exception as e:
                raise EndpointResolutionError(
                    f"Failed to fetch endpoint '{endpoint}': {e}",
                    endpoint_path=endpoint,
                ) from e

            # Recurse with EndpointPublic
            return self._resolve_endpoint_ref(ep, expected_type=expected_type)

        raise TypeError(f"Cannot resolve endpoint from type: {type(endpoint)}")

    def _collect_unique_owners(
        self,
        model_ref: EndpointRef,
        data_source_refs: list[EndpointRef],
    ) -> list[str]:
        """Collect unique owner usernames from all endpoints.

        Used to determine which satellite tokens need to be fetched.

        Args:
            model_ref: The model endpoint reference
            data_source_refs: List of data source endpoint references

        Returns:
            List of unique owner usernames
        """
        owners: set[str] = set()

        if model_ref.owner_username:
            owners.add(model_ref.owner_username)

        for ds in data_source_refs:
            if ds.owner_username:
                owners.add(ds.owner_username)

        return list(owners)

    def _get_satellite_tokens_for_owners(
        self,
        owners: list[str],
    ) -> dict[str, str]:
        """Get satellite tokens for all unique endpoint owners.

        Args:
            owners: List of owner usernames

        Returns:
            Dict mapping owner username to satellite token
        """
        if not owners:
            return {}

        return self._auth.get_satellite_tokens(owners)

    def _collect_tunneling_usernames(
        self,
        model_ref: EndpointRef,
        data_source_refs: list[EndpointRef],
    ) -> list[str]:
        """Check if any endpoints use tunneling URLs and extract target usernames.

        Args:
            model_ref: The model endpoint reference
            data_source_refs: List of data source endpoint references

        Returns:
            List of unique tunneling usernames
        """
        usernames: set[str] = set()

        if model_ref.url.startswith(TUNNELING_PREFIX):
            usernames.add(model_ref.url[len(TUNNELING_PREFIX) :])

        for ds in data_source_refs:
            if ds.url.startswith(TUNNELING_PREFIX):
                usernames.add(ds.url[len(TUNNELING_PREFIX) :])

        return list(usernames)

    def _get_transaction_tokens_for_owners(
        self,
        owners: list[str],
    ) -> dict[str, str]:
        """Get transaction tokens for billing authorization.

        Transaction tokens pre-authorize endpoint owners to charge
        the current user for usage.

        Args:
            owners: List of owner usernames

        Returns:
            Dict mapping owner username to transaction token
        """
        if not owners:
            return {}

        response = self._auth.get_transaction_tokens(owners)
        return response.get("tokens", {})

    def _build_request_body(
        self,
        prompt: str,
        model_ref: EndpointRef,
        data_source_refs: list[EndpointRef],
        endpoint_tokens: dict[str, str],
        transaction_tokens: dict[str, str],
        *,
        top_k: int = 5,
        max_tokens: int = 1024,
        temperature: float = 0.7,
        similarity_threshold: float = 0.5,
        stream: bool = False,
        messages: list[dict[str, str]] | None = None,
        peer_token: str | None = None,
        peer_channel: str | None = None,
    ) -> dict[str, Any]:
        """Build the request body for the aggregator.

        Includes endpoint_tokens mapping for satellite token authentication
        and transaction_tokens for billing authorization.
        User identity is derived from satellite tokens, not passed in request body.
        """
        body: dict[str, Any] = {
            "prompt": prompt,
            "model": {
                "url": model_ref.url,
                "slug": model_ref.slug,
                "name": model_ref.name,
                "tenant_name": model_ref.tenant_name,
                "owner_username": model_ref.owner_username,
            },
            "data_sources": [
                {
                    "url": ds.url,
                    "slug": ds.slug,
                    "name": ds.name,
                    "tenant_name": ds.tenant_name,
                    "owner_username": ds.owner_username,
                }
                for ds in data_source_refs
            ],
            "endpoint_tokens": endpoint_tokens,
            "transaction_tokens": transaction_tokens,
            "top_k": top_k,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "similarity_threshold": similarity_threshold,
            "stream": stream,
        }
        if messages:
            body["messages"] = messages

        # Include peer token fields for NATS tunneling
        if peer_token:
            body["peer_token"] = peer_token
        if peer_channel:
            body["peer_channel"] = peer_channel

        return body

    def _handle_aggregator_error(self, response: httpx.Response) -> None:
        """Handle error responses from the aggregator."""
        try:
            data = response.json()
            message = data.get("message", data.get("error", str(data)))
        except Exception:
            message = response.text or f"HTTP {response.status_code}"

        raise AggregatorError(
            message=f"Aggregator error: {message}",
            status_code=response.status_code,
            detail=response.text,
        )

    def _parse_sse_event(
        self, event_type: str, data: dict[str, Any]
    ) -> ChatStreamEvent:
        """Parse an SSE event into a typed event object."""
        if event_type == "retrieval_start":
            return RetrievalStartEvent(source_count=data.get("sources", 0))

        elif event_type == "source_complete":
            return SourceCompleteEvent(
                path=data.get("path", ""),
                status=data.get("status", ""),
                documents_retrieved=data.get("documents", 0),
            )

        elif event_type == "retrieval_complete":
            return RetrievalCompleteEvent(
                total_documents=data.get("total_documents", 0),
                time_ms=data.get("time_ms", 0),
            )

        elif event_type == "reranking_start":
            return RerankingStartEvent(documents=data.get("documents", 0))

        elif event_type == "reranking_complete":
            return RerankingCompleteEvent(
                documents=data.get("documents", 0),
                time_ms=data.get("time_ms", 0),
            )

        elif event_type == "generation_start":
            return GenerationStartEvent()

        elif event_type == "generation_heartbeat":
            return GenerationHeartbeatEvent(elapsed_ms=data.get("elapsed_ms", 0))

        elif event_type == "token":
            return TokenEvent(content=data.get("content", ""))

        elif event_type == "done":
            # Parse document sources (new format: dict of title -> {slug, content})
            sources: dict[str, DocumentSource] = {}
            sources_data = data.get("sources", {})
            if isinstance(sources_data, dict):
                for title, source_data in sources_data.items():
                    if isinstance(source_data, dict):
                        sources[title] = DocumentSource(
                            slug=source_data.get("slug", ""),
                            content=source_data.get("content", ""),
                        )

            # Parse retrieval info (metadata about each data source retrieval)
            retrieval_info: list[SourceInfo] = []
            for s in data.get("retrieval_info", []):
                retrieval_info.append(
                    SourceInfo(
                        path=s.get("path", ""),
                        documents_retrieved=s.get("documents_retrieved", 0),
                        status=SourceStatus(s.get("status", "success")),
                        error_message=s.get("error_message"),
                    )
                )

            metadata = None
            if "metadata" in data:
                m = data["metadata"]
                metadata = ChatMetadata(
                    retrieval_time_ms=m.get("retrieval_time_ms", 0),
                    generation_time_ms=m.get("generation_time_ms", 0),
                    total_time_ms=m.get("total_time_ms", 0),
                )

            # Parse usage if available (only from non-streaming mode)
            usage = None
            if "usage" in data:
                u = data["usage"]
                usage = TokenUsage(
                    prompt_tokens=u.get("prompt_tokens", 0),
                    completion_tokens=u.get("completion_tokens", 0),
                    total_tokens=u.get("total_tokens", 0),
                )

            return DoneEvent(
                sources=sources,
                retrieval_info=retrieval_info,
                metadata=metadata,
                usage=usage,
            )

        elif event_type == "error":
            return ErrorEvent(message=data.get("message", "Unknown error"))

        # Unknown event type - return as error
        logger.warning(f"Unknown SSE event type: {event_type}")
        return ErrorEvent(message=f"Unknown event type: {event_type}")

    def complete(
        self,
        prompt: str,
        model: str | EndpointRef | EndpointPublic,
        data_sources: list[str | EndpointRef | EndpointPublic] | None = None,
        *,
        top_k: int = 5,
        max_tokens: int = 1024,
        temperature: float = 0.7,
        similarity_threshold: float = 0.5,
        aggregator_url: str | None = None,
        messages: list[dict[str, str]] | None = None,
    ) -> ChatResponse:
        """Send a chat request and get the complete response.

        This method automatically:
        1. Resolves endpoints and extracts owner information
        2. Exchanges Hub tokens for satellite tokens (one per unique owner)
        3. Sends tokens to the aggregator for forwarding to SyftAI-Space

        Args:
            prompt: The user's question or prompt
            model: Model endpoint (path string, EndpointRef, or EndpointPublic)
            data_sources: Optional list of data source endpoints for context
            top_k: Number of documents to retrieve per source (default: 5)
            max_tokens: Maximum tokens to generate (default: 1024)
            temperature: Generation temperature (default: 0.7)
            similarity_threshold: Minimum similarity for retrieved docs (default: 0.5)
            aggregator_url: Custom aggregator URL (optional, uses default if not provided)

        Returns:
            ChatResponse with response text, sources, and metadata

        Raises:
            EndpointResolutionError: If endpoint cannot be resolved
            AggregatorError: If aggregator service fails
            ValueError: If endpoint type is wrong

        Example:
            response = client.chat.complete(
                prompt="What is machine learning?",
                model="alice/gpt-4-endpoint",
                data_sources=["bob/ml-docs"],
            )
            print(response.response)
            print(f"Used {len(response.sources)} sources")
        """
        # Use custom aggregator URL if provided, otherwise use default
        effective_aggregator_url = (aggregator_url or self._aggregator_url).rstrip("/")

        model_ref = self._resolve_endpoint_ref(model, expected_type="model")

        ds_refs = []
        for ds in data_sources or []:
            ds_refs.append(self._resolve_endpoint_ref(ds, expected_type="data_source"))

        # Get satellite tokens and transaction tokens for all unique endpoint owners
        unique_owners = self._collect_unique_owners(model_ref, ds_refs)
        endpoint_tokens = self._get_satellite_tokens_for_owners(unique_owners)
        transaction_tokens = self._get_transaction_tokens_for_owners(unique_owners)

        # Auto-fetch peer token if tunneling endpoints detected
        peer_token = None
        peer_channel = None
        tunneling_usernames = self._collect_tunneling_usernames(model_ref, ds_refs)
        if tunneling_usernames:
            peer_response = self._auth.get_peer_token(tunneling_usernames)
            peer_token = peer_response.peer_token
            peer_channel = peer_response.peer_channel

        request_body = self._build_request_body(
            prompt=prompt,
            model_ref=model_ref,
            data_source_refs=ds_refs,
            endpoint_tokens=endpoint_tokens,
            transaction_tokens=transaction_tokens,
            top_k=top_k,
            max_tokens=max_tokens,
            temperature=temperature,
            similarity_threshold=similarity_threshold,
            stream=False,
            messages=messages,
            peer_token=peer_token,
            peer_channel=peer_channel,
        )

        try:
            response = self._agg_client.post(
                f"{effective_aggregator_url}/chat",
                json=request_body,
                headers={"Content-Type": "application/json"},
            )
        except httpx.RequestError as e:
            raise AggregatorError(
                f"Failed to connect to aggregator: {e}",
                detail=str(e),
            ) from e

        if response.status_code >= 400:
            self._handle_aggregator_error(response)

        data = response.json()

        # Parse document sources (new format: dict of title -> {slug, content})
        sources: dict[str, DocumentSource] = {}
        sources_data = data.get("sources", {})
        if isinstance(sources_data, dict):
            for title, source_data in sources_data.items():
                if isinstance(source_data, dict):
                    sources[title] = DocumentSource(
                        slug=source_data.get("slug", ""),
                        content=source_data.get("content", ""),
                    )

        # Parse retrieval info (metadata about each data source retrieval)
        retrieval_info: list[SourceInfo] = []
        for s in data.get("retrieval_info", []):
            retrieval_info.append(
                SourceInfo(
                    path=s.get("path", ""),
                    documents_retrieved=s.get("documents_retrieved", 0),
                    status=SourceStatus(s.get("status", "success")),
                    error_message=s.get("error_message"),
                )
            )

        # Parse metadata
        m = data.get("metadata", {})
        metadata = ChatMetadata(
            retrieval_time_ms=m.get("retrieval_time_ms", 0),
            generation_time_ms=m.get("generation_time_ms", 0),
            total_time_ms=m.get("total_time_ms", 0),
        )

        # Parse usage if available
        usage = None
        if "usage" in data and data["usage"]:
            u = data["usage"]
            usage = TokenUsage(
                prompt_tokens=u.get("prompt_tokens", 0),
                completion_tokens=u.get("completion_tokens", 0),
                total_tokens=u.get("total_tokens", 0),
            )

        return ChatResponse(
            response=data.get("response", ""),
            sources=sources,
            retrieval_info=retrieval_info,
            metadata=metadata,
            usage=usage,
        )

    def stream(
        self,
        prompt: str,
        model: str | EndpointRef | EndpointPublic,
        data_sources: list[str | EndpointRef | EndpointPublic] | None = None,
        *,
        top_k: int = 5,
        max_tokens: int = 1024,
        temperature: float = 0.7,
        similarity_threshold: float = 0.5,
        aggregator_url: str | None = None,
        messages: list[dict[str, str]] | None = None,
    ) -> Iterator[ChatStreamEvent]:
        """Send a chat request and stream response events.

        This method automatically:
        1. Resolves endpoints and extracts owner information
        2. Exchanges Hub tokens for satellite tokens (one per unique owner)
        3. Sends tokens to the aggregator for forwarding to SyftAI-Space

        Args:
            prompt: The user's question or prompt
            model: Model endpoint (path string, EndpointRef, or EndpointPublic)
            data_sources: Optional list of data source endpoints for context
            top_k: Number of documents to retrieve per source (default: 5)
            max_tokens: Maximum tokens to generate (default: 1024)
            temperature: Generation temperature (default: 0.7)
            similarity_threshold: Minimum similarity for retrieved docs (default: 0.5)
            aggregator_url: Custom aggregator URL (optional, uses default if not provided)

        Yields:
            ChatStreamEvent objects as they arrive

        Event types:
            - RetrievalStartEvent: Retrieval phase beginning
            - SourceCompleteEvent: A data source finished querying
            - RetrievalCompleteEvent: All retrieval complete
            - GenerationStartEvent: Model generation starting
            - TokenEvent: A token from the model response
            - DoneEvent: Generation complete with final metadata
            - ErrorEvent: An error occurred

        Example:
            for event in client.chat.stream(
                prompt="Explain AI",
                model="alice/gpt-4-endpoint",
            ):
                if event.type == "token":
                    print(event.content, end="", flush=True)
                elif event.type == "done":
                    print(f"\\nCompleted in {event.metadata.total_time_ms}ms")
        """
        # Use custom aggregator URL if provided, otherwise use default
        effective_aggregator_url = (aggregator_url or self._aggregator_url).rstrip("/")

        model_ref = self._resolve_endpoint_ref(model, expected_type="model")

        ds_refs = []
        for ds in data_sources or []:
            ds_refs.append(self._resolve_endpoint_ref(ds, expected_type="data_source"))

        # Get satellite tokens and transaction tokens for all unique endpoint owners
        unique_owners = self._collect_unique_owners(model_ref, ds_refs)
        endpoint_tokens = self._get_satellite_tokens_for_owners(unique_owners)
        transaction_tokens = self._get_transaction_tokens_for_owners(unique_owners)

        # Auto-fetch peer token if tunneling endpoints detected
        peer_token = None
        peer_channel = None
        tunneling_usernames = self._collect_tunneling_usernames(model_ref, ds_refs)
        if tunneling_usernames:
            peer_response = self._auth.get_peer_token(tunneling_usernames)
            peer_token = peer_response.peer_token
            peer_channel = peer_response.peer_channel

        request_body = self._build_request_body(
            prompt=prompt,
            model_ref=model_ref,
            data_source_refs=ds_refs,
            endpoint_tokens=endpoint_tokens,
            transaction_tokens=transaction_tokens,
            top_k=top_k,
            max_tokens=max_tokens,
            temperature=temperature,
            similarity_threshold=similarity_threshold,
            stream=True,
            messages=messages,
            peer_token=peer_token,
            peer_channel=peer_channel,
        )

        try:
            with self._agg_client.stream(
                "POST",
                f"{effective_aggregator_url}/chat/stream",
                json=request_body,
                headers={
                    "Content-Type": "application/json",
                    "Accept": "text/event-stream",
                },
            ) as response:
                if response.status_code >= 400:
                    # Read the error response
                    response.read()
                    self._handle_aggregator_error(response)

                # Parse SSE stream
                current_event: str | None = None
                current_data: str = ""

                for line in response.iter_lines():
                    line = line.strip()

                    if not line:
                        # Empty line = end of event
                        if current_event and current_data:
                            try:
                                data = json.loads(current_data)
                                yield self._parse_sse_event(current_event, data)
                            except json.JSONDecodeError as e:
                                logger.warning(f"Failed to parse SSE data: {e}")
                                yield ErrorEvent(message=f"Parse error: {e}")

                        current_event = None
                        current_data = ""
                        continue

                    if line.startswith("event:"):
                        current_event = line[6:].strip()
                    elif line.startswith("data:"):
                        current_data = line[5:].strip()

        except httpx.RequestError as e:
            raise AggregatorError(
                f"Failed to connect to aggregator: {e}",
                detail=str(e),
            ) from e

    def get_available_models(
        self,
        *,
        limit: int = 20,
    ) -> Iterator[EndpointPublic]:
        """Get model endpoints that have connection URLs configured.

        This is a convenience method for discovering models that can be
        used with the chat API. It filters the hub for model endpoints
        that have at least one enabled connection with a URL.

        Args:
            limit: Maximum number of results (default: 20)

        Yields:
            EndpointPublic objects for models with URLs

        Example:
            for model in client.chat.get_available_models():
                print(f"{model.owner_username}/{model.slug}: {model.name}")
        """
        count = 0
        for endpoint in self._hub.browse():
            if count >= limit:
                break

            # Filter for models with URLs
            if endpoint.type != EndpointType.MODEL:
                continue

            # Check if has enabled connection with URL
            has_url = any(
                conn.enabled and conn.config.get("url") for conn in endpoint.connect
            )
            if has_url:
                yield endpoint
                count += 1

    def get_available_data_sources(
        self,
        *,
        limit: int = 20,
    ) -> Iterator[EndpointPublic]:
        """Get data source endpoints that have connection URLs configured.

        This is a convenience method for discovering data sources that can be
        used with the chat API. It filters the hub for data source endpoints
        that have at least one enabled connection with a URL.

        Args:
            limit: Maximum number of results (default: 20)

        Yields:
            EndpointPublic objects for data sources with URLs

        Example:
            for source in client.chat.get_available_data_sources():
                print(f"{source.owner_username}/{source.slug}: {source.name}")
        """
        count = 0
        for endpoint in self._hub.browse():
            if count >= limit:
                break

            # Filter for data sources with URLs
            if endpoint.type != EndpointType.DATA_SOURCE:
                continue

            # Check if has enabled connection with URL
            has_url = any(
                conn.enabled and conn.config.get("url") for conn in endpoint.connect
            )
            if has_url:
                yield endpoint
                count += 1
