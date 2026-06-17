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

    def close(self) -> None:
        """Close the SyftAI-Space HTTP client."""
        self._client.close()

    def _build_headers(
        self,
        tenant_name: str | None = None,
        authorization_token: str | None = None,
    ) -> dict[str, str]:
        """Build headers for SyftAI-Space request."""
        headers = {
            "Content-Type": "application/json",
        }
        if tenant_name:
            headers["X-Tenant-Name"] = tenant_name
        if authorization_token:
            headers["Authorization"] = f"Bearer {authorization_token}"
        return headers

    def _mint_satellite_token(self, audience: str) -> str | None:
        """Mint a satellite token for ``audience`` (the endpoint owner's username).

        Mirrors the aggregator's token coordination layer (``query.py``): try an
        authenticated token first, then fall back to a guest token. Returns
        ``None`` if both fail, so the caller can still attempt an
        unauthenticated request (preserving the previous behaviour).
        """
        if self._http.is_authenticated:
            try:
                data = self._http.get("/api/v1/token", params={"aud": audience})
                if isinstance(data, dict) and data.get("target_token"):
                    return str(data["target_token"])
            except Exception:
                logger.debug(
                    "Authenticated satellite token failed for '%s'; trying guest",
                    audience,
                )
        try:
            data = self._http.get(
                "/api/v1/token/guest",
                params={"aud": audience},
                include_auth=False,
            )
            if isinstance(data, dict) and data.get("target_token"):
                return str(data["target_token"])
        except Exception:
            logger.debug("Guest satellite token failed for '%s'", audience)
        return None

    def _pay_mpp(self, www_authenticate: str, slug: str) -> str | None:
        """Pay an MPP ``402`` challenge via the Hub wallet, return an X-Payment credential.

        Mirrors the aggregator's ``mpp_payment.handle_mpp_payment``: the
        ``WWW-Authenticate`` challenge is forwarded verbatim to the Hub's
        ``/api/v1/wallet/pay``, which parses it and returns an ``x_payment``
        string to attach to a retry. Returns ``None`` if no challenge was given.
        """
        if not www_authenticate:
            return None
        data = self._http.post(
            "/api/v1/wallet/pay",
            json={"www_authenticate": www_authenticate, "endpoint_slug": slug},
        )
        if isinstance(data, dict) and data.get("x_payment"):
            return str(data["x_payment"])
        return None

    @staticmethod
    def _endpoint_query_url(endpoint: EndpointRef) -> str:
        return f"{endpoint.url.rstrip('/')}/api/v1/endpoints/{endpoint.slug}/query"

    @staticmethod
    def _extract_error_message(response: httpx.Response) -> str:
        """Extract a human-readable error message from a response body."""
        try:
            error_data = response.json()
            return str(
                error_data.get("detail", error_data.get("message", str(error_data)))
            )
        except Exception:
            return response.text or f"HTTP {response.status_code}"

    def _post_endpoint(
        self,
        endpoint: EndpointRef,
        body: dict[str, object],
        *,
        error_cls: type[RetrievalError | GenerationError],
        error_prefix: str,
        authorization_token: str | None = None,
        pay: bool = False,
        **error_kwargs: str,
    ) -> httpx.Response:
        """POST to an endpoint, mapping connection/HTTP errors to error_cls.

        If the endpoint replies ``402 Payment Required`` and ``pay`` is set, the
        MPP challenge is settled via the Hub wallet and the request is retried
        once with the resulting ``X-Payment`` credential — mirroring how the
        aggregator's ``DataSourceClient.query`` handles payment at this layer.
        """
        query_url = self._endpoint_query_url(endpoint)
        headers = self._build_headers(endpoint.tenant_name, authorization_token)
        try:
            response = self._client.post(query_url, json=body, headers=headers)
        except httpx.RequestError as e:
            raise error_cls(
                f"Failed to connect to {error_prefix} '{endpoint.slug}': {e}",
                detail=str(e),
                **error_kwargs,
            ) from e

        # MPP 402 payment flow: pay via the Hub wallet, then retry with X-Payment.
        if response.status_code == 402 and pay:
            try:
                x_payment = self._pay_mpp(
                    response.headers.get("www-authenticate", ""), endpoint.slug
                )
            except httpx.HTTPError as e:
                raise error_cls(
                    f"Payment failed for {error_prefix} '{endpoint.slug}': {e}",
                    detail=str(e),
                    **error_kwargs,
                ) from e
            if x_payment:
                try:
                    response = self._client.post(
                        query_url,
                        json=body,
                        headers={**headers, "X-Payment": x_payment},
                    )
                except httpx.RequestError as e:
                    raise error_cls(
                        f"Failed to connect to {error_prefix} '{endpoint.slug}': {e}",
                        detail=str(e),
                        **error_kwargs,
                    ) from e

        if response.status_code >= 400:
            message = self._extract_error_message(response)
            raise error_cls(
                f"{error_prefix.capitalize()} query failed: {message}",
                detail=response.text,
                **error_kwargs,
            )

        return response

    def query_data_source(
        self,
        endpoint: EndpointRef,
        query: str,
        user_email: str,
        *,
        top_k: int = 5,
        similarity_threshold: float = 0.5,
        authorization_token: str | None = None,
        owner_username: str | None = None,
        pay: bool = False,
    ) -> list[Document]:
        """Query a data source endpoint directly.

        Sends a query to a SyftAI-Space data source endpoint and returns
        the retrieved documents.

        Authentication mirrors the aggregator: SyftAI-Space endpoints expect a
        satellite bearer token whose audience is the endpoint owner's username.
        If ``authorization_token`` is not supplied, one is minted automatically
        when an owner is known (``owner_username`` argument or
        ``endpoint.owner_username``).

        Args:
            endpoint: EndpointRef with URL and slug
            query: The search query
            user_email: User email for visibility/policy checks
            top_k: Number of documents to retrieve (default: 5)
            similarity_threshold: Minimum similarity score (default: 0.5)
            authorization_token: Pre-minted satellite token. If omitted, one is
                minted from the resolved owner username.
            owner_username: Endpoint owner username used as the satellite-token
                audience. Falls back to ``endpoint.owner_username``.
            pay: If True, settle an MPP ``402 Payment Required`` challenge via the
                Hub wallet and retry. If False (default), a ``402`` raises
                ``RetrievalError``.

        Returns:
            List of Document objects

        Raises:
            RetrievalError: If the query fails

        Example:
            docs = client.syftai.query_data_source(
                endpoint=EndpointRef(
                    url="http://syftai:8080", slug="docs", owner_username="alice"
                ),
                query="What is machine learning?",
                user_email="alice@example.com",
                pay=True,  # auto-pay if the endpoint is metered
            )
            for doc in docs:
                print(f"[{doc.score:.2f}] {doc.content[:100]}...")
        """
        token = authorization_token
        if token is None:
            audience = owner_username or endpoint.owner_username
            if audience:
                token = self._mint_satellite_token(audience)

        request_body = {
            "user_email": user_email,
            "messages": query,  # SyftAI-Space expects "messages" for query text
            "limit": top_k,
            "similarity_threshold": similarity_threshold,
        }

        response = self._post_endpoint(
            endpoint,
            request_body,
            error_cls=RetrievalError,
            error_prefix="data source",
            authorization_token=token,
            pay=pay,
            source_path=endpoint.slug,
        )

        return self._parse_documents(response.json())

    @staticmethod
    def _parse_documents(data: dict[str, object]) -> list[Document]:
        """Parse documents from a SyftAI-Space query response.

        Mirrors the aggregator's ``DataSourceClient._parse_syftai_response``:
        the canonical shape nests documents under ``references.documents`` and
        names the score ``similarity_score``. A legacy top-level ``documents``
        list (with ``score``) is still honoured for backward compatibility.
        """
        references = data.get("references")
        if isinstance(references, dict):
            raw_docs = references.get("documents", [])
            score_key = "similarity_score"
        else:
            raw_docs = data.get("documents", [])
            score_key = "score"

        documents: list[Document] = []
        if isinstance(raw_docs, list):
            for doc in raw_docs:
                if not isinstance(doc, dict):
                    continue
                raw_score = doc.get(score_key, doc.get("score", 0.0))
                documents.append(
                    Document(
                        content=doc.get("content", ""),
                        score=float(raw_score or 0.0),
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
        request_body = {
            "user_email": user_email,
            "messages": [
                {"role": msg.role, "content": msg.content} for msg in messages
            ],
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": False,
        }

        response = self._post_endpoint(
            endpoint,
            request_body,
            error_cls=GenerationError,
            error_prefix="model",
            model_slug=endpoint.slug,
        )

        data = response.json()

        # Extract response text from message
        message = data.get("message", {})
        content: str = message.get("content", "")
        return content

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
                self._endpoint_query_url(endpoint),
                json=request_body,
                headers={
                    **self._build_headers(endpoint.tenant_name),
                    "Accept": "text/event-stream",
                },
            ) as response:
                if response.status_code >= 400:
                    response.read()
                    message = self._extract_error_message(response)

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
