"""Clients package - HTTP clients for external services."""

from aggregator.clients.data_source import DataSourceClient
from aggregator.clients.model import ModelClient, ModelClientError
from aggregator.clients.syfthub import (
    EndpointAccessDeniedError,
    EndpointNotFoundError,
    SyftHubClient,
    SyftHubClientError,
)
from aggregator.clients.tunnel import (
    TunnelClient,
    TunnelClientError,
    extract_tunnel_username,
    is_tunneled_url,
)

__all__ = [
    "SyftHubClient",
    "SyftHubClientError",
    "EndpointNotFoundError",
    "EndpointAccessDeniedError",
    "DataSourceClient",
    "ModelClient",
    "ModelClientError",
    "TunnelClient",
    "TunnelClientError",
    "is_tunneled_url",
    "extract_tunnel_username",
]
