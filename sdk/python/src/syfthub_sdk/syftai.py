"""SyftAI-Space resource for direct endpoint queries.

This module provides low-level access to SyftAI-Space endpoints, allowing
users to build custom RAG pipelines or bypass the aggregator service.

Example usage:
    # Query a data source directly
    docs = client.syftai.query_data_source(
        endpoint=EndpointRef(url="http://syftai:8080", slug="docs"),
        query="What is machine learning?",
        user_email="alice@example.com",
    )

    # Query a model directly
    response = client.syftai.query_model(
        endpoint=EndpointRef(url="http://syftai:8080", slug="gpt-model"),
        messages=[
            Message(role="system", content="You are a helpful assistant."),
            Message(role="user", content="Hello!"),
        ],
        user_email="alice@example.com",
    )

    # Stream model response
    for chunk in client.syftai.query_model_stream(
        endpoint=model_ref,
        messages=messages,
        user_email="alice@example.com",
    ):
        print(chunk, end="")
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from typing import TYPE_CHECKING

import httpx

from syfthub_sdk.exceptions import GenerationError, RetrievalError
from syfthub_sdk.models import Document, EndpointRef, Message

if TYPE_CHECKING:
    from syfthub_sdk._http import HTTPClient

logger = logging.getLogger(__name__)


class SyftAIResource:
    """Low-level resource for direct SyftAI-Space endpoint queries.

    This resource provides direct access to SyftAI-Space endpoints without
    going through the aggregator. Use this when you need:
    - Custom RAG pipelines with specific retrieval strategies
    - Direct model queries without data source context
    - Fine-grained control over the query process

    For most use cases, prefer the higher-level `client.chat` API instead.

    Example:
        # Build a custom RAG pipeline
        # 1. Query data sources
        docs = client.syftai.query_data_source(
            endpoint=data_source_ref,
            query="What is Python?",
            user_email="alice@example.com",
            top_k=10,
        )

        # 2. Build custom prompt
        context = "\\n".join(doc.content for doc in docs)
        messages = [
            Message(role="system", content=f"Context:\\n{context}"),
            Message(role="user", content="What is Python?"),
        ]

        # 3. Query model
        response = client.syftai.query_model(
            endpoint=model_ref,
            messages=messages,
            user_email="alice@example.com",
        )
        print(response)
    """

    def __init__(
        self,
        http: HTTPClient,
    ) -> None:
        """Initialize SyftAI resource.

        Args:
            http: HTTP client (for auth validation)
        """
        self._http = http
        # Client for SyftAI-Space with reasonable timeout
        self._client = httpx.Client(timeout=60.0)

    def _build_headers(
        self,
        tenant_name: str | None = None,
    ) -> dict[str, str]:
        """Build headers for SyftAI-Space request."""
        headers = {
            "Content-Type": "application/json",
        }
        if tenant_name:
            headers["X-Tenant-Name"] = tenant_name
        return headers

    def query_data_source(
        self,
        endpoint: EndpointRef,
        query: str,
        user_email: str,
        *,
        top_k: int = 5,
        similarity_threshold: float = 0.5,
    ) -> list[Document]:
        """Query a data source endpoint directly.

        Sends a query to a SyftAI-Space data source endpoint and returns
        the retrieved documents.

        Args:
            endpoint: EndpointRef with URL and slug
            query: The search query
            user_email: User email for visibility/policy checks
            top_k: Number of documents to retrieve (default: 5)
            similarity_threshold: Minimum similarity score (default: 0.5)

        Returns:
            List of Document objects

        Raises:
            RetrievalError: If the query fails

        Example:
            docs = client.syftai.query_data_source(
                endpoint=EndpointRef(url="http://syftai:8080", slug="docs"),
                query="What is machine learning?",
                user_email="alice@example.com",
            )
            for doc in docs:
                print(f"[{doc.score:.2f}] {doc.content[:100]}...")
        """
        url = f"{endpoint.url.rstrip('/')}/api/v1/endpoints/{endpoint.slug}/query"

        request_body = {
            "user_email": user_email,
            "messages": query,  # SyftAI-Space expects "messages" for query text
            "limit": top_k,
            "similarity_threshold": similarity_threshold,
        }

        try:
            response = self._client.post(
                url,
                json=request_body,
                headers=self._build_headers(endpoint.tenant_name),
            )
        except httpx.RequestError as e:
            raise RetrievalError(
                f"Failed to connect to data source '{endpoint.slug}': {e}",
                source_path=endpoint.slug,
                detail=str(e),
            ) from e

        if response.status_code >= 400:
            try:
                error_data = response.json()
                message = error_data.get(
                    "detail", error_data.get("message", str(error_data))
                )
            except Exception:
                message = response.text or f"HTTP {response.status_code}"

            raise RetrievalError(
                f"Data source query failed: {message}",
                source_path=endpoint.slug,
                detail=response.text,
            )

        data = response.json()
        documents = []

        for doc in data.get("documents", []):
            documents.append(
                Document(
                    content=doc.get("content", ""),
                    score=doc.get("score", 0.0),
                    metadata=doc.get("metadata", {}),
                )
            )

        return documents

    def query_model(
        self,
        endpoint: EndpointRef,
        messages: list[Message],
        user_email: str,
        *,
        max_tokens: int = 1024,
        temperature: float = 0.7,
    ) -> str:
        """Query a model endpoint directly.

        Sends messages to a SyftAI-Space model endpoint and returns
        the generated response.

        Args:
            endpoint: EndpointRef with URL and slug
            messages: List of chat messages
            user_email: User email for visibility/policy checks
            max_tokens: Maximum tokens to generate (default: 1024)
            temperature: Generation temperature (default: 0.7)

        Returns:
            Generated response text

        Raises:
            GenerationError: If generation fails

        Example:
            response = client.syftai.query_model(
                endpoint=EndpointRef(url="http://syftai:8080", slug="gpt-model"),
                messages=[
                    Message(role="system", content="You are helpful."),
                    Message(role="user", content="Hello!"),
                ],
                user_email="alice@example.com",
            )
            print(response)
        """
        url = f"{endpoint.url.rstrip('/')}/api/v1/endpoints/{endpoint.slug}/query"

        request_body = {
            "user_email": user_email,
            "messages": [
                {"role": msg.role, "content": msg.content} for msg in messages
            ],
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": False,
        }

        try:
            response = self._client.post(
                url,
                json=request_body,
                headers=self._build_headers(endpoint.tenant_name),
            )
        except httpx.RequestError as e:
            raise GenerationError(
                f"Failed to connect to model '{endpoint.slug}': {e}",
                model_slug=endpoint.slug,
                detail=str(e),
            ) from e

        if response.status_code >= 400:
            try:
                error_data = response.json()
                message = error_data.get(
                    "detail", error_data.get("message", str(error_data))
                )
            except Exception:
                message = response.text or f"HTTP {response.status_code}"

            raise GenerationError(
                f"Model query failed: {message}",
                model_slug=endpoint.slug,
                detail=response.text,
            )

        data = response.json()

        # Extract response text from message
        message = data.get("message", {})
        return message.get("content", "")

    def query_model_stream(
        self,
        endpoint: EndpointRef,
        messages: list[Message],
        user_email: str,
        *,
        max_tokens: int = 1024,
        temperature: float = 0.7,
    ) -> Iterator[str]:
        """Stream a model response directly.

        Sends messages to a SyftAI-Space model endpoint and streams
        the generated response tokens.

        Args:
            endpoint: EndpointRef with URL and slug
            messages: List of chat messages
            user_email: User email for visibility/policy checks
            max_tokens: Maximum tokens to generate (default: 1024)
            temperature: Generation temperature (default: 0.7)

        Yields:
            Response text chunks as they arrive

        Raises:
            GenerationError: If generation fails

        Example:
            for chunk in client.syftai.query_model_stream(
                endpoint=model_ref,
                messages=messages,
                user_email="alice@example.com",
            ):
                print(chunk, end="", flush=True)
        """
        url = f"{endpoint.url.rstrip('/')}/api/v1/endpoints/{endpoint.slug}/query"

        request_body = {
            "user_email": user_email,
            "messages": [
                {"role": msg.role, "content": msg.content} for msg in messages
            ],
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": True,
        }

        try:
            with self._client.stream(
                "POST",
                url,
                json=request_body,
                headers={
                    **self._build_headers(endpoint.tenant_name),
                    "Accept": "text/event-stream",
                },
            ) as response:
                if response.status_code >= 400:
                    response.read()
                    try:
                        error_data = json.loads(response.text)
                        message = error_data.get(
                            "detail", error_data.get("message", str(error_data))
                        )
                    except Exception:
                        message = response.text or f"HTTP {response.status_code}"

                    raise GenerationError(
                        f"Model stream failed: {message}",
                        model_slug=endpoint.slug,
                        detail=response.text,
                    )

                # Parse SSE stream
                for line in response.iter_lines():
                    line = line.strip()
                    if not line or line.startswith("event:"):
                        continue

                    if line.startswith("data:"):
                        data_str = line[5:].strip()
                        if data_str == "[DONE]":
                            break

                        try:
                            data = json.loads(data_str)
                            # Extract content from various response formats
                            if "content" in data:
                                yield data["content"]
                            elif "choices" in data:
                                # OpenAI-style response
                                for choice in data["choices"]:
                                    delta = choice.get("delta", {})
                                    if "content" in delta:
                                        yield delta["content"]
                        except json.JSONDecodeError:
                            # Skip malformed data
                            pass

        except httpx.RequestError as e:
            raise GenerationError(
                f"Failed to connect to model '{endpoint.slug}': {e}",
                model_slug=endpoint.slug,
                detail=str(e),
            ) from e
