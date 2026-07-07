"""Unit tests for SearchResource (retrieval-only via the Aggregator)."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
import respx

from syfthub_sdk import SyftHubClient
from syfthub_sdk.exceptions import AggregatorError
from syfthub_sdk.models import AuthTokens, EndpointRef, SearchDocument, SearchResponse


@pytest.fixture
def base_url() -> str:
    return "https://test.syfthub.com"


@pytest.fixture
def aggregator_url(base_url: str) -> str:
    return f"{base_url}/aggregator/api/v1"


@pytest.fixture
def fake_tokens() -> AuthTokens:
    return AuthTokens(
        access_token="fake-access-token",
        refresh_token="fake-refresh-token",
    )


@pytest.fixture
def mock_search_response() -> dict[str, Any]:
    """Aggregator retrieval-only response: empty text, populated sources map."""
    return {
        "response": "",
        "sources": {
            "EPFL News #1": {"slug": "epfl-news/epfl-news", "content": "First story."},
            "EPFL News #2": {"slug": "epfl-news/epfl-news", "content": "Second story."},
        },
        "retrieval_info": [
            {
                "path": "epfl-news/epfl-news",
                "documents_retrieved": 2,
                "status": "success",
            }
        ],
        "metadata": {
            "retrieval_time_ms": 120,
            "generation_time_ms": 0,
            "total_time_ms": 120,
        },
        "billing": {
            "total_cost": 0.03,
            "currency": "USD",
            "entries": [
                {
                    "source": "epfl-news/epfl-news",
                    "policy_type": "mpp_per_request",
                    "kind": "payment",
                    "status": "charged",
                    "amount": 0.03,
                    "currency": "USD",
                    "recipient": {"username": "epfl-news"},
                    "transaction": {"rail": "mpp", "id": "0xsearch"},
                    "details": {},
                }
            ],
        },
    }


@pytest.fixture
def mock_satellite_token_response() -> dict[str, Any]:
    return {"target_token": "fake-satellite-token", "expires_in": 3600}


class TestSearchQuery:
    """Tests for SearchResource.query()."""

    @respx.mock
    def test_query_returns_documents(
        self,
        base_url: str,
        aggregator_url: str,
        fake_tokens: AuthTokens,
        mock_search_response: dict[str, Any],
        mock_satellite_token_response: dict[str, Any],
    ) -> None:
        respx.get(f"{base_url}/api/v1/token").mock(
            return_value=httpx.Response(200, json=mock_satellite_token_response)
        )
        respx.post(f"{aggregator_url}/chat").mock(
            return_value=httpx.Response(200, json=mock_search_response)
        )

        client = SyftHubClient(base_url=base_url)
        client._http.set_tokens(fake_tokens)

        ds = EndpointRef(
            url="http://20.0.5.93:8081",
            slug="epfl-news",
            owner_username="epfl-news",
        )
        response = client.search.query(prompt="What happened?", data_sources=[ds])

        assert isinstance(response, SearchResponse)
        assert len(response.documents) == 2
        assert all(isinstance(d, SearchDocument) for d in response.documents)
        assert {d.content for d in response.documents} == {
            "First story.",
            "Second story.",
        }
        assert response.documents[0].slug == "epfl-news/epfl-news"
        assert response.retrieval_info[0].documents_retrieved == 2
        assert response.metadata.generation_time_ms == 0
        # Billing block is surfaced on retrieval-only responses too.
        assert response.billing is not None
        assert response.billing.total_cost == 0.03
        assert response.billing.entries[0].source == "epfl-news/epfl-news"
        assert response.billing.entries[0].transaction is not None
        assert response.billing.entries[0].transaction.id == "0xsearch"

    @respx.mock
    def test_query_sends_retrieval_only_and_user_token(
        self,
        base_url: str,
        aggregator_url: str,
        fake_tokens: AuthTokens,
        mock_search_response: dict[str, Any],
        mock_satellite_token_response: dict[str, Any],
    ) -> None:
        """The aggregator request must flag retrieval_only and forward the
        user token (so metered sources can be paid server-side)."""
        respx.get(f"{base_url}/api/v1/token").mock(
            return_value=httpx.Response(200, json=mock_satellite_token_response)
        )
        route = respx.post(f"{aggregator_url}/chat").mock(
            return_value=httpx.Response(200, json=mock_search_response)
        )

        client = SyftHubClient(base_url=base_url)
        client._http.set_tokens(fake_tokens)

        ds = EndpointRef(
            url="http://20.0.5.93:8081", slug="epfl-news", owner_username="epfl-news"
        )
        client.search.query(prompt="hi", data_sources=[ds])

        sent = json.loads(route.calls.last.request.content)
        assert sent["retrieval_only"] is True
        assert sent["user_token"] == "fake-access-token"
        # Placeholder model is present but empty (never contacted by aggregator).
        assert sent["model"]["url"] == ""
        assert sent["model"]["slug"] == ""

    @respx.mock
    def test_query_guest_mode_omits_user_token(
        self,
        base_url: str,
        aggregator_url: str,
        mock_search_response: dict[str, Any],
    ) -> None:
        respx.get(f"{base_url}/api/v1/token/guest").mock(
            return_value=httpx.Response(200, json={"target_token": "guest-tok"})
        )
        route = respx.post(f"{aggregator_url}/chat").mock(
            return_value=httpx.Response(200, json=mock_search_response)
        )

        client = SyftHubClient(base_url=base_url)
        ds = EndpointRef(
            url="http://20.0.5.93:8081", slug="epfl-news", owner_username="epfl-news"
        )
        client.search.query(prompt="hi", data_sources=[ds], guest_mode=True)

        sent = json.loads(route.calls.last.request.content)
        assert sent["retrieval_only"] is True
        assert "user_token" not in sent

    @respx.mock
    def test_query_aggregator_error(
        self,
        base_url: str,
        aggregator_url: str,
        fake_tokens: AuthTokens,
    ) -> None:
        respx.post(f"{aggregator_url}/chat").mock(
            return_value=httpx.Response(500, json={"message": "boom"})
        )

        client = SyftHubClient(base_url=base_url)
        client._http.set_tokens(fake_tokens)

        ds = EndpointRef(url="http://20.0.5.93:8081", slug="epfl-news")
        with pytest.raises(AggregatorError, match="boom"):
            client.search.query(prompt="hi", data_sources=[ds])

    def test_search_resource_is_cached(self, base_url: str) -> None:
        client = SyftHubClient(base_url=base_url)
        assert client.search is client.search
