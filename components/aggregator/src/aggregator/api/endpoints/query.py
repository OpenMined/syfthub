"""Server-side query endpoint for curl/fetch access.

Provides a GET endpoint that accepts the same URL format as the frontend /q route,
resolves endpoints and tokens server-side, runs the RAG pipeline, and returns
a static HTML page with the JSON result embedded.

Usage:
    curl "http://localhost:8080/aggregator/api/v1/q?q=owner/slug1|owner/slug2!prompt"
"""

import asyncio
import logging
from typing import Annotated, Any

import httpx
from fastapi import APIRouter, Depends, Query
from fastapi.responses import HTMLResponse

from aggregator.api.dependencies import get_optional_token, get_orchestrator
from aggregator.core.config import get_settings
from aggregator.schemas import ChatRequest, EndpointRef
from aggregator.services import Orchestrator, OrchestratorError
from aggregator.templates.query_result import render_query_result_html

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/q", tags=["query"])

_REQUEST_TIMEOUT = 10.0


def _parse_query_param(q: str) -> tuple[list[str], str] | str:
    """Parse the q parameter. Returns (data_sources, prompt) or error string."""
    bang_index = q.find("!")
    if bang_index == -1:
        return "Invalid query format: missing '!' separator. Expected: owner/slug1|owner/slug2!your+query"

    prompt = q[bang_index + 1 :].strip()
    if not prompt:
        return "Empty prompt: add your question after the '!'."

    slug_part = q[:bang_index]
    data_sources = [s.strip() for s in slug_part.split("|") if s.strip()] if slug_part else []

    for slug in data_sources:
        if "/" not in slug:
            return f"Invalid endpoint format '{slug}'. Expected owner/slug (e.g. openmined/wiki)."

    return (data_sources, prompt)


async def _resolve_endpoint(
    client: httpx.AsyncClient, path: str, base_url: str, user_token: str | None
) -> EndpointRef:
    """Resolve an endpoint path via the SyftHub backend API.

    Returns an EndpointRef ready for use in ChatRequest.
    Raises httpx or value errors on failure.
    """
    headers: dict[str, str] = {"Accept": "application/json"}
    if user_token:
        headers["Authorization"] = f"Bearer {user_token}"

    resp = await client.get(f"{base_url}/{path}", headers=headers)
    resp.raise_for_status()
    data = resp.json()

    # Extract first enabled connection with a URL
    url = None
    tenant_name = None
    for conn in data.get("connect", []):
        if conn.get("enabled", True) and conn.get("config", {}).get("url"):
            url = str(conn["config"]["url"])
            tenant_name = conn["config"].get("tenant_name")
            break

    if not url:
        raise ValueError(f"Endpoint '{path}' has no connection URL configured.")

    return EndpointRef(
        url=url,
        slug=data.get("slug", path.split("/")[-1]),
        name=data.get("name", ""),
        owner_username=data.get("owner_username"),
        tenant_name=tenant_name,
    )


async def _get_guest_satellite_token(
    client: httpx.AsyncClient, audience: str, base_url: str
) -> str | None:
    """Fetch a guest satellite token from the backend."""
    try:
        resp = await client.get(f"{base_url}/api/v1/token/guest", params={"aud": audience})
        resp.raise_for_status()
        token: str | None = resp.json().get("target_token")
        return token
    except httpx.HTTPError:
        logger.warning("Failed to get guest satellite token for audience '%s'", audience)
        return None


async def _get_satellite_token(
    client: httpx.AsyncClient, audience: str, user_token: str, base_url: str
) -> str | None:
    """Fetch an authenticated satellite token from the backend."""
    try:
        resp = await client.get(
            f"{base_url}/api/v1/token",
            params={"aud": audience},
            headers={"Authorization": f"Bearer {user_token}"},
        )
        resp.raise_for_status()
        token: str | None = resp.json().get("target_token")
        return token
    except httpx.HTTPError:
        logger.warning(
            "Failed to get satellite token for audience '%s', falling back to guest",
            audience,
        )
        return await _get_guest_satellite_token(client, audience, base_url)


def _error_result(query: str, model: str, data_sources: list[str], error: str) -> dict[str, Any]:
    return {
        "query": query,
        "model": model,
        "data_sources": data_sources,
        "answer": None,
        "sources": {},
        "error": error,
    }


@router.get("")
async def query_render(
    q: Annotated[str, Query(description="Query in format: owner/slug1|owner/slug2!your+prompt")],
    orchestrator: Annotated[Orchestrator, Depends(get_orchestrator)],
    user_token: Annotated[str | None, Depends(get_optional_token)],
) -> HTMLResponse:
    """
    Execute a query from a URL and return a static HTML page with the result.

    This endpoint is designed for curl/fetch access — no JavaScript required.
    It parses the ``q`` parameter, resolves endpoints, acquires satellite tokens,
    runs the full RAG pipeline, and returns self-contained HTML.

    **Format:** ``/q?q=owner/slug1|owner/slug2!your+prompt``

    - Pipe-delimited data source slugs before ``!``
    - User prompt after ``!``
    - Empty data source section is valid (model-only query)

    **Examples:**

    - ``/q?q=alice/wiki!what+is+machine+learning``
    - ``/q?q=alice/wiki|bob/docs!compare+approaches``
    - ``/q?q=!hello+world`` (model-only, no data sources)
    """
    settings = get_settings()
    default_model = settings.default_query_model
    base_url = settings.syfthub_url.rstrip("/")

    # --- Parse ---
    parsed = _parse_query_param(q)
    if isinstance(parsed, str):
        return HTMLResponse(
            content=render_query_result_html(_error_result(q, default_model, [], parsed)),
            status_code=400,
        )

    data_source_slugs, prompt = parsed

    async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT) as client:
        # --- Resolve all endpoints in parallel ---
        all_slugs = [default_model, *data_source_slugs]
        resolve_results = await asyncio.gather(
            *[_resolve_endpoint(client, slug, base_url, user_token) for slug in all_slugs],
            return_exceptions=True,
        )

        # Check for resolution failures
        resolved: list[EndpointRef] = []
        for i, res in enumerate(resolve_results):
            if isinstance(res, BaseException):
                slug = all_slugs[i]
                label = "model" if i == 0 else f"data source '{slug}'"
                logger.warning("Failed to resolve %s: %s", label, res)
                return HTMLResponse(
                    content=render_query_result_html(
                        _error_result(
                            prompt,
                            default_model,
                            data_source_slugs,
                            f"Failed to resolve {label}. Check the slug and ensure the endpoint exists.",
                        )
                    ),
                    status_code=502,
                )
            resolved.append(res)

        model_ref = resolved[0]
        ds_refs = resolved[1:]

        # --- Acquire satellite tokens in parallel ---
        unique_owners: list[str] = list(
            {ref.owner_username for ref in resolved if ref.owner_username}
        )
        is_guest = user_token is None

        async def _fetch_token(owner: str) -> tuple[str, str | None]:
            if is_guest:
                return (owner, await _get_guest_satellite_token(client, owner, base_url))
            assert user_token is not None  # narrowing for type checker
            return (owner, await _get_satellite_token(client, owner, user_token, base_url))

        token_results = await asyncio.gather(*[_fetch_token(owner) for owner in unique_owners])
        endpoint_tokens = {owner: token for owner, token in token_results if token}

    # --- Build ChatRequest and run pipeline ---
    model_path = (
        f"{model_ref.owner_username}/{model_ref.slug}"
        if model_ref.owner_username
        else model_ref.slug
    )

    chat_request = ChatRequest(
        prompt=prompt,
        model=model_ref,
        data_sources=ds_refs,
        endpoint_tokens=endpoint_tokens,
    )

    try:
        response = await orchestrator.process_chat(chat_request, user_token)
        result = {
            "query": prompt,
            "model": model_path,
            "data_sources": data_source_slugs,
            "answer": response.response,
            "sources": {
                title: {"slug": src.slug, "content": src.content}
                for title, src in response.sources.items()
            },
            "error": None,
        }
    except OrchestratorError as exc:
        logger.error("Orchestration error in query render: %s", exc)
        result = _error_result(prompt, model_path, data_source_slugs, str(exc))
        return HTMLResponse(content=render_query_result_html(result), status_code=502)
    except Exception:
        logger.exception("Unexpected error in query render endpoint")
        result = _error_result(
            prompt, model_path, data_source_slugs, "An unexpected error occurred."
        )
        return HTMLResponse(content=render_query_result_html(result), status_code=500)

    return HTMLResponse(content=render_query_result_html(result))
