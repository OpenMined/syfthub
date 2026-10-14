"""Base classes and the ``to_dict()`` / ``from_dict()`` conventions.

Every model serialises to plain JSON: Decimals as strings, datetimes as ISO 8601, enums as their
values, wire names via aliases. Unknown server fields are never rejected; they stay in ``raw``.
"""

from __future__ import annotations

from typing import Any, TypeVar

from pydantic import BaseModel, ConfigDict, PrivateAttr
from pydantic import ValidationError as _PydanticValidationError

from ..errors import ValidationError
from .ports import HubPorts

T = TypeVar("T", bound="Base")
B = TypeVar("B", bound="Bound")

# ``Frozen`` and the bound models that must not change after validation share this.
FROZEN = ConfigDict(extra="ignore", populate_by_name=True, frozen=True)


def _hashable(value: Any) -> Any:
    """A field value as something ``hash`` accepts: dicts and lists become tuples."""
    if isinstance(value, dict):
        return tuple(sorted((k, _hashable(v)) for k, v in value.items()))
    if isinstance(value, (list, tuple)):
        return tuple(_hashable(v) for v in value)
    if isinstance(value, (set, frozenset)):
        return frozenset(_hashable(v) for v in value)
    return value


class Base(BaseModel):
    """Shared config: ignore unknown keys, accept field names and aliases alike."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    def to_dict(self) -> dict[str, Any]:
        """Plain-JSON dict with wire names. Safe to store; never carries a hub reference."""
        return self.model_dump(mode="json", by_alias=True)

    # Equality and hashing look at the same field values, never at the private hub binding, so
    # an object read back with ``from_dict(hub, d)`` equals the one that was stored, and
    # ``Money.of("1.0")`` hashes like ``Money.of("1.00")`` because the Decimals are equal.
    def __eq__(self, other: object) -> bool:
        if type(other) is not type(self):
            return NotImplemented
        return self.__dict__ == other.__dict__

    def __hash__(self) -> int:
        return hash((type(self).__qualname__, _hashable(self.__dict__)))


class Frozen(Base):
    """Immutable data object. Hashable, so it can sit in tuples and sets."""

    model_config = FROZEN

    @classmethod
    def from_dict(cls: type[T], d: dict[str, Any]) -> T:
        return _validate(cls, d)


class Bound(Base):
    """A model that can call the network through a hub it is bound to.

    The hub lives in a private attribute, never in a field, so ``to_dict()`` stays storable and
    ``from_dict(hub, d)`` re-binds. Subclasses override ``_bind`` to bind nested objects too.
    Binding says nothing about mutability: a bound model that must not change sets ``FROZEN``.
    """

    _hub: HubPorts | None = PrivateAttr(default=None)

    @classmethod
    def from_dict(cls: type[B], hub: HubPorts, d: dict[str, Any]) -> B:
        obj = _validate(cls, d)
        obj._bind(hub)
        return obj

    def _bind(self, hub: HubPorts) -> None:
        self._hub = hub

    def _derive(self: B, **update: Any) -> B:
        """``model_copy(update=...)`` that keeps the binding: a view of a bound object is bound,
        a view of a stored one stays unbound."""
        new = self.model_copy(update=update)
        if self._hub is not None:
            new._bind(self._hub)
        return new

    def _require_hub(self) -> HubPorts:
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
