"""Domain package for business entities and value objects."""

from syfthub.domain.base_url import (
    MAX_BASE_URL_LENGTH,
    TUNNELING_PREFIX,
    BaseUrl,
    normalize_base_url,
)
from syfthub.domain.exceptions import (
    ConflictError,
    DomainException,
    NotFoundError,
    PermissionDeniedError,
    ValidationError,
)
from syfthub.domain.satellite import (
    AmbiguousSatelliteError,
    SatelliteKind,
    SatelliteKindMismatchError,
    SatelliteRef,
)
from syfthub.domain.value_objects import ValueObject

__all__ = [
    "MAX_BASE_URL_LENGTH",
    "TUNNELING_PREFIX",
    "AmbiguousSatelliteError",
    "BaseUrl",
    "ConflictError",
    "DomainException",
    "NotFoundError",
    "PermissionDeniedError",
    "SatelliteKind",
    "SatelliteKindMismatchError",
    "SatelliteRef",
    "ValidationError",
    "ValueObject",
    "normalize_base_url",
]
