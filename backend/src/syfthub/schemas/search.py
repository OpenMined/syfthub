"""Search-related Pydantic schemas.

This module defines schemas for the semantic search endpoint that uses
RAG (Retrieval-Augmented Generation) to find relevant endpoints.
"""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field

from syfthub.schemas.endpoint import Connection, EndpointType, Policy


class EndpointSearchRequest(BaseModel):
    """Request schema for semantic endpoint search."""

    query: str = Field(
        ...,
        min_length=1,
        max_length=1000,
        description="Natural language search query",
        examples=["machine learning model for text classification"],
    )
    top_k: int = Field(
        default=10,
        ge=1,
        le=50,
        description="Maximum number of results to return",
    )
    type: Optional[EndpointType] = Field(
        default=None,
        description="Filter results by endpoint type (model, data_source, or model_data_source)",
    )


class EndpointSearchResult(BaseModel):
    """Schema for a single search result with relevance score."""

    # All fields from EndpointPublicResponse
    name: str = Field(..., description="Display name of the endpoint")
    slug: str = Field(..., description="URL-safe identifier")
    description: str = Field(..., description="Description of the endpoint")
    type: EndpointType = Field(
        ..., description="Type of endpoint (model, data_source, or model_data_source)"
    )
    owner_username: str = Field(..., description="Username of the endpoint owner")
    contributors_count: int = Field(
        ..., description="Number of contributors to this endpoint"
    )
    version: str = Field(..., description="Semantic version of the endpoint")
    readme: str = Field(..., description="Markdown content for the README")
    tags: List[str] = Field(..., description="List of tags for categorization")
    stars_count: int = Field(
        ..., description="Number of stars this endpoint has received"
    )
    policies: List[Policy] = Field(
        ..., description="List of policies applied to this endpoint"
    )
    connect: List[Connection] = Field(
        ..., description="List of connection methods available for this endpoint"
    )
    created_at: datetime = Field(..., description="When the endpoint was created")
    updated_at: datetime = Field(..., description="When the endpoint was last updated")

    # Search-specific fields
    relevance_score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Relevance score from semantic search (0.0-1.0, higher is more relevant)",
    )

    model_config = {"from_attributes": True}


class EndpointSearchResponse(BaseModel):
    """Response schema for semantic endpoint search."""

    results: List[EndpointSearchResult] = Field(
        ...,
        description="List of matching endpoints with relevance scores, ordered by relevance",
    )
    total: int = Field(
        ...,
        ge=0,
        description="Total number of results returned",
    )
    query: str = Field(
        ...,
        description="The original search query",
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "results": [
                        {
                            "name": "GPT Text Classifier",
                            "slug": "gpt-text-classifier",
                            "description": "A text classification model using GPT",
                            "type": "model",
                            "owner_username": "alice",
                            "contributors_count": 3,
                            "version": "1.0.0",
                            "readme": "# GPT Text Classifier\n\nA model for...",
                            "tags": ["ml", "nlp", "classification"],
                            "stars_count": 42,
                            "policies": [],
                            "connect": [],
                            "created_at": "2024-01-15T10:30:00Z",
                            "updated_at": "2024-01-20T14:45:00Z",
                            "relevance_score": 0.92,
                        }
                    ],
                    "total": 1,
                    "query": "text classification model",
                }
            ]
        }
    }
