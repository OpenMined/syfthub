"""Base classes and the ``to_dict()`` / ``from_dict()`` conventions.

Every model serialises to plain JSON: Decimals as strings, datetimes as ISO 8601, enums as their
values, wire names via aliases. Unknown server fields are never rejected; they stay in ``raw``.
"""

from __future__ import annotations

from typing import Any, TypeVar

from pydantic import BaseModel, ConfigDict, PrivateAttr
from pydantic import ValidationError as _PydanticValidationError

from ..errors import ValidationError

T = TypeVar("T", bound="Base")
B = TypeVar("B", bound="Bound")


class Base(BaseModel):
    """Shared config: ignore unknown keys, accept field names and aliases alike."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    def to_dict(self) -> dict[str, Any]:
        """Plain-JSON dict with wire names. Safe to store; never carries a hub reference."""
        return self.model_dump(mode="json", by_alias=True)

    # Equality and hashing look at fields only, never at the private hub binding, so an object
    # read back with ``from_dict(hub, d)`` equals the one that was stored.
    def __eq__(self, other: object) -> bool:
        if type(other) is not type(self):
            return NotImplemented
        return self.__dict__ == other.__dict__

    def __hash__(self) -> int:
        return hash((type(self).__qualname__, self.model_dump_json(by_alias=True)))


class Frozen(Base):
    """Immutable data object. Hashable, so it can sit in tuples and sets."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True, frozen=True)

    @classmethod
    def from_dict(cls: type[T], d: dict[str, Any]) -> T:
        return _validate(cls, d)


class Bound(Base):
    """A model that can call the network through a hub it is bound to.

    The hub lives in a private attribute, never in a field, so ``to_dict()`` stays storable and
    ``from_dict(hub, d)`` re-binds. Subclasses override ``_bind`` to bind nested objects too.
    """

    model_config = ConfigDict(extra="ignore", populate_by_name=True, frozen=True)

    _hub: Any = PrivateAttr(default=None)

    @classmethod
    def from_dict(cls: type[B], hub: Any, d: dict[str, Any]) -> B:
        obj = _validate(cls, d)
        obj._bind(hub)
        return obj

    def _bind(self, hub: Any) -> None:
        self._hub = hub

    def _require_hub(self) -> Any:
        if self._hub is None:
            raise ValidationError(
                f"{type(self).__name__} is not bound to a hub; "
                f"rebuild it with {type(self).__name__}.from_dict(hub, d)"
            )
        return self._hub


def _validate(cls: type[T], d: dict[str, Any]) -> T:
    try:
        return cls.model_validate(d)
    except _PydanticValidationError as e:
        raise ValidationError(str(e)) from e
