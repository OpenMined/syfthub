"""Private, hand-written route clients over the Hub and Space HTTP APIs. No business logic here."""

from .detail import ErrorDetail, detail_of
from .hub import HubApi
from .space import SpaceApi

__all__ = ["ErrorDetail", "detail_of", "HubApi", "SpaceApi"]
