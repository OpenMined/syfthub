"""Satellite domain types.

A **satellite** is a service owned by a Hub account that receives satellite
tokens on its behalf — a space (serves endpoints) or a station (hosts a Managed
Wallet). The codebase already calls the receiving side a "satellite service";
a satellite token is a token *for* a satellite.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING

from syfthub.domain.exceptions import DomainException, ValidationError

if TYPE_CHECKING:
    from syfthub.domain.base_url import BaseUrl


class SatelliteKind(str, Enum):
    """What a satellite is.

    A kind, not a subclass: spaces and stations differ in validation, not
    behaviour. Stored as a string, like every other enum in this schema.
    """

    SPACE = "space"
    """Serves endpoints. Reports its own base URL."""

    STATION = "station"
    """Hosts a Managed Wallet and calls ``/verify``. Serves no endpoints."""


@dataclass(frozen=True)
class SatelliteRef:
    """An identified satellite, detached from the ORM session.

    Frozen because it is the resolved answer to "which satellite is this write
    for" — a security-relevant decision that must not change between resolution
    and use. Also makes it hashable and cheap to compare.

    Carries both identifiers: ``id`` for foreign keys and joins, ``public_id``
    for API responses and a token's ``aud``. Separating them is what makes
    ``public_id`` rotatable without re-keying a row.

    ``id`` must never be serialised.
    """

    id: int
    public_id: uuid.UUID
    user_id: int
    kind: SatelliteKind
    base_url: BaseUrl
    created_at: datetime
    last_seen_at: datetime | None


class AmbiguousSatelliteError(ValidationError):
    """A write could belong to more than one satellite.

    Single-satellite accounts never hit this. It fires when an account owns a
    second satellite and sends a write that does not say which one — guessing
    would attribute data to the wrong host. Mapped to 422.
    """

    def __init__(self, count: int):
        """Initialize ambiguous satellite error."""
        self.count = count
        super().__init__(
            f"This account owns {count} satellites; specify which one this "
            f"request is for via satellite_id"
        )


class SatelliteKindMismatchError(DomainException):
    """An origin is already registered under the other kind.

    Registration is idempotent on the origin, so re-registering one the account
    already holds is normal. Re-registering it as a *different* kind is not: a
    host is either a space or a station, and silently returning the other would
    attach endpoints to a station or mint the wrong audience.
    """

    def __init__(self, expected: SatelliteKind, actual: SatelliteKind):
        """Initialize satellite kind mismatch error."""
        self.expected = expected
        self.actual = actual
        super().__init__(
            f"That origin is already registered as a {actual.value}, "
            f"not a {expected.value}",
            "SATELLITE_KIND_MISMATCH",
        )


class UnknownDestinationError(ValidationError):
    """No satellite of the audience's account serves the requested destination.

    This refusal is the point of binding tokens to satellites. A policy naming
    ``credits_url = https://evil.example.com`` with ``wallet_owner = bob``
    resolves that URL inside *bob's* satellites, finds nothing, and no token is
    minted — so there is nothing for the attacker to collect, whatever any
    receiver later checks.
    """

    def __init__(self, destination: str):
        """Initialize unknown destination error."""
        self.destination = destination
        super().__init__(
            f"No registered satellite serves '{destination}' for that account"
        )


__all__ = [
    "AmbiguousSatelliteError",
    "SatelliteKind",
    "SatelliteKindMismatchError",
    "SatelliteRef",
    "UnknownDestinationError",
]
