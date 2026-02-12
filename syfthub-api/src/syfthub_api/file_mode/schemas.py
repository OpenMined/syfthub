"""
Pydantic schemas for file-based endpoint configuration.

This module defines the data models for parsing README.md frontmatter
and policy YAML configurations.
"""

from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

# Slug validation pattern (same as in app.py)
_SLUG_PATTERN = re.compile(r"^[a-z0-9]([a-z0-9_-]{0,62}[a-z0-9])?$")

# Validation constants
_MAX_NAME_LENGTH = 100
_MAX_DESCRIPTION_LENGTH = 500


class EnvConfig(BaseModel):
    """
    Environment variable configuration for an endpoint.

    Allows declaring required/optional env vars and inheritance from parent.

    Example in README.md frontmatter:
        ---
        env:
          required:
            - OPENAI_API_KEY
          optional:
            - DEBUG_MODE
          inherit:
            - PATH
            - HOME
        ---
    """

    required: list[str] = Field(
        default_factory=list,
        description="Environment variables that must be defined in .env",
    )
    optional: list[str] = Field(
        default_factory=list,
        description="Environment variables that may be defined in .env",
    )
    inherit: list[str] = Field(
        default_factory=list,
        description="Environment variables to inherit from parent process",
    )


class RuntimeConfig(BaseModel):
    """
    Runtime execution configuration for an endpoint.

    Controls how the endpoint handler is executed:
    - in_process: Direct execution in main process (default, fastest)
    - subprocess: Isolated execution in subprocess with virtual environment
    - container: Maximum isolation using Docker containers (future)

    Example in README.md frontmatter:
        ---
        runtime:
          mode: subprocess
          workers: 2
          timeout: 30
          extras:
            - ml
        ---
    """

    mode: Literal["in_process", "subprocess", "container"] = Field(
        default="in_process",
        description="Execution mode: 'in_process', 'subprocess', or 'container'",
    )
    workers: int = Field(
        default=2,
        ge=1,
        le=16,
        description="Number of worker processes for subprocess/container mode",
    )
    timeout: int = Field(
        default=30,
        ge=1,
        le=300,
        description="Execution timeout in seconds",
    )
    idle_timeout: int = Field(
        default=300,
        ge=30,
        le=3600,
        description="Idle worker timeout before cleanup (seconds)",
    )
    extras: list[str] = Field(
        default_factory=list,
        description="Optional dependency extras to install (from pyproject.toml)",
    )
    python_version: str | None = Field(
        default=None,
        description="Python version for venv (default: same as host)",
    )


class EndpointConfig(BaseModel):
    """
    Configuration parsed from README.md YAML frontmatter.

    Example frontmatter:
        ---
        slug: my-endpoint
        type: model
        name: My Endpoint
        description: Optional description
        enabled: true
        env:
          required:
            - API_KEY
        ---
    """

    slug: str = Field(..., description="URL-safe identifier for the endpoint")
    type: Literal["model", "data_source"] = Field(
        ..., description="Endpoint type: 'model' or 'data_source'"
    )
    name: str = Field(..., max_length=_MAX_NAME_LENGTH, description="Human-readable name")
    description: str = Field(
        default="",
        max_length=_MAX_DESCRIPTION_LENGTH,
        description="Optional endpoint description",
    )
    enabled: bool = Field(default=True, description="Whether the endpoint is active")
    version: str = Field(default="1.0", description="Endpoint version for tracking")
    env: EnvConfig = Field(
        default_factory=EnvConfig,
        description="Environment variable configuration",
    )
    runtime: RuntimeConfig = Field(
        default_factory=RuntimeConfig,
        description="Runtime execution configuration",
    )

    @field_validator("slug")
    @classmethod
    def validate_slug(cls, v: str) -> str:
        """Validate slug format matches existing pattern."""
        if not v:
            raise ValueError("Endpoint slug cannot be empty")
        if not _SLUG_PATTERN.match(v):
            raise ValueError(
                f"Invalid slug '{v}'. Slugs must be 1-64 characters, "
                "lowercase alphanumeric with hyphens/underscores allowed, "
                "and must start with a letter or number."
            )
        return v

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        """Validate name is not empty."""
        if not v or not v.strip():
            raise ValueError("Endpoint name cannot be empty")
        return v.strip()

    @field_validator("description")
    @classmethod
    def validate_description(cls, v: str) -> str:
        """Normalize description."""
        return v.strip() if v else ""


class PolicyConfig(BaseModel):
    """
    Configuration parsed from policy/*.yaml files.

    Example YAML:
        type: RateLimitPolicy
        name: my_rate_limit
        config:
          max_requests: 100
          window_seconds: 60

    For composite policies (AllOf, AnyOf):
        type: AllOf
        name: premium_gate
        policies:
          - type: AccessGroupPolicy
            config:
              users: ["alice", "bob"]
          - type: TokenLimitPolicy
            config:
              max_input_tokens: 2000
    """

    type: str = Field(..., description="Policy class name (e.g., 'RateLimitPolicy')")
    name: str | None = Field(
        default=None, description="Policy instance name (auto-generated if not provided)"
    )
    config: dict[str, Any] = Field(
        default_factory=dict, description="Policy configuration parameters"
    )
    policies: list[PolicyConfig] | None = Field(
        default=None, description="Child policies for composite types (AllOf, AnyOf, Not)"
    )

    @field_validator("type")
    @classmethod
    def validate_type(cls, v: str) -> str:
        """Validate policy type is not empty."""
        if not v or not v.strip():
            raise ValueError("Policy type cannot be empty")
        return v.strip()


class FileEndpointDefinition(BaseModel):
    """
    Complete runtime representation of a file-based endpoint.

    This combines the parsed configuration with runtime metadata
    like source path for hot-reload tracking.
    """

    config: EndpointConfig = Field(..., description="Parsed endpoint configuration")
    source_path: str = Field(..., description="Absolute path to endpoint folder")
    readme_content: str = Field(
        default="", description="README content after frontmatter (documentation)"
    )
    policies_loaded: int = Field(
        default=0, description="Number of policies successfully loaded"
    )

    model_config = {"frozen": False}
