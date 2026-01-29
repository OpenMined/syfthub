"""Clients package - HTTP and NATS clients for external services."""

from aggregator.clients.data_source import DataSourceClient
from aggregator.clients.model import ModelClient, ModelClientError
from aggregator.clients.nats_transport import NATSTransport, NATSTransportError
from aggregator.clients.syfthub import (
    EndpointAccessDeniedError,
    EndpointNotFoundError,
    SyftHubClient,
    SyftHubClientError,
)

__all__ = [
    "SyftHubClient",
    "SyftHubClientError",
    "EndpointNotFoundError",
    "EndpointAccessDeniedError",
    "DataSourceClient",
    "ModelClient",
    "ModelClientError",
    "NATSTransport",
    "NATSTransportError",
]
