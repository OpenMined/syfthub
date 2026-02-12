"""Clients package - HTTP clients for external services."""

from aggregator.clients.data_source import DataSourceClient
from aggregator.clients.error_reporter import ErrorReporter
from aggregator.clients.model import ModelClient, ModelClientError
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
]
