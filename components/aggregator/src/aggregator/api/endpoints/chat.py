"""Chat endpoints for the aggregator API."""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from aggregator.api.dependencies import get_optional_token, get_orchestrator
from aggregator.schemas import ChatRequest, ChatResponse, ErrorResponse
from aggregator.services import Orchestrator, OrchestratorError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post(
    "",
    response_model=ChatResponse,
    responses={
        400: {"model": ErrorResponse, "description": "Bad request"},
        500: {"model": ErrorResponse, "description": "Internal server error"},
    },
)
async def chat(
    request: ChatRequest,
    orchestrator: Annotated[Orchestrator, Depends(get_orchestrator)],
    user_token: Annotated[str | None, Depends(get_optional_token)],
) -> ChatResponse:
    """
    Process a chat request with RAG context aggregation.

    This endpoint:
    1. Resolves the model and data source endpoints from SyftHub
    2. Queries each data source for relevant documents (in parallel)
    3. Builds an augmented prompt with the retrieved context
    4. Sends the prompt to the model endpoint
    5. Returns the generated response with source attribution

    **Request:**
    - `prompt`: The user's question or prompt
    - `model`: Path to the model endpoint (e.g., "owner/slug")
    - `data_sources`: Optional list of data source paths
    - `top_k`: Number of documents to retrieve per source (default: 5)

    **Response:**
    - `response`: The generated answer from the model
    - `sources`: Information about each data source queried
    - `metadata`: Timing information (retrieval, generation, total)
    """
    try:
        return await orchestrator.process_chat(request, user_token)
    except OrchestratorError as e:
        logger.error(f"Orchestration error: {e}")
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        logger.exception("Unexpected error in chat endpoint")
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.post(
    "/stream",
    responses={
        400: {"model": ErrorResponse, "description": "Bad request"},
        500: {"model": ErrorResponse, "description": "Internal server error"},
    },
)
async def chat_stream(
    request: ChatRequest,
    orchestrator: Annotated[Orchestrator, Depends(get_orchestrator)],
    user_token: Annotated[str | None, Depends(get_optional_token)],
) -> StreamingResponse:
    """
    Process a chat request with streaming response.

    Returns a Server-Sent Events (SSE) stream with the following event types:

    **Retrieval Phase:**
    - `retrieval_start`: `{"sources": N}` - Starting to query N data sources
    - `source_complete`: `{"path": "...", "status": "...", "documents": N}` - One source done
    - `retrieval_complete`: `{"total_documents": N, "time_ms": N}` - All sources done

    **Generation Phase:**
    - `generation_start`: `{}` - Starting model generation
    - `token`: `{"content": "..."}` - A chunk of the response
    - `done`: `{"sources": [...], "metadata": {...}}` - Complete with final metadata

    **Error:**
    - `error`: `{"message": "..."}` - An error occurred
    """
    # Force stream=True in the request, preserving all other fields
    request_with_stream = request.model_copy(update={"stream": True})

    return StreamingResponse(
        orchestrator.process_chat_stream(request_with_stream, user_token),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        },
    )
