"""Satellite domain types.

A **satellite** is a service owned by a Hub account that receives satellite
tokens on its behalf — a space (serves endpoints) or a station (hosts a Managed
Wallet). The codebase already calls the receiving side a "satellite service";
a satellite token is a token *for* a satellite.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

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
    slug: str
    base_url: BaseUrl | None


__all__ = ["SatelliteKind", "SatelliteRef"]
