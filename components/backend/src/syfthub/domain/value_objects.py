"""Value objects for domain modeling.

Note: These value objects are available for future use but currently
validation is handled directly by Pydantic schemas.
"""

from __future__ import annotations

from typing import Any

from syfthub.domain.exceptions import ValidationError


class ValueObject:
    """Base class for value objects."""

    def __init__(self, value: Any):
        """Initialize value object."""
        self._validate(value)
        self._value = value

    def _validate(self, value: Any) -> None:
        """Validate value (to be implemented by subclasses)."""
        pass

    @property
    def value(self) -> Any:
        """Get the value."""
        return self._value

    def __str__(self) -> str:
        """String representation."""
        return str(self._value)

    def __repr__(self) -> str:
        """Detailed representation."""
        return f"{self.__class__.__name__}('{self._value}')"

    def __eq__(self, other: object) -> bool:
        """Equality comparison."""
        if isinstance(other, self.__class__):
            return bool(self._value == other._value)
        return False

    def __hash__(self) -> int:
        """Hash for use in sets and dicts."""
        return hash(self._value)


__all__ = ["ValidationError", "ValueObject"]
