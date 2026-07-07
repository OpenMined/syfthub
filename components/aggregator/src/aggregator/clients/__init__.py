"""Clients package - HTTP and NATS clients for external services."""

from aggregator.clients.data_source import DataSourceClient
from aggregator.clients.error_reporter import ErrorReporter
from aggregator.clients.model import ModelClient, ModelClientError
from aggregator.clients.mpp_payment import handle_mpp_payment
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
    "ErrorReporter",
    "ModelClient",
    "ModelClientError",
    "NATSTransport",
    "NATSTransportError",
    "handle_mpp_payment",
]
