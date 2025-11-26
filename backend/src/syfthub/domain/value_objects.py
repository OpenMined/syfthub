"""Value objects for domain modeling."""

from __future__ import annotations

import re
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


class Email(ValueObject):
    """Email value object with validation."""

    def _validate(self, value: str) -> None:
        """Validate email format."""
        if not value or not isinstance(value, str):
            raise ValidationError("Email cannot be empty")

        # Basic email validation
        email_pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
        if not re.match(email_pattern, value):
            raise ValidationError("Invalid email format")

        if len(value) > 255:
            raise ValidationError("Email too long (max 255 characters)")


class Username(ValueObject):
    """Username value object with validation."""

    def _validate(self, value: str) -> None:
        """Validate username format."""
        if not value or not isinstance(value, str):
            raise ValidationError("Username cannot be empty")

        if len(value) < 3:
            raise ValidationError("Username must be at least 3 characters long")

        if len(value) > 50:
            raise ValidationError("Username too long (max 50 characters)")

        # Username can contain letters, numbers, hyphens, underscores
        if not re.match(r"^[a-zA-Z0-9_-]+$", value):
            raise ValidationError(
                "Username can only contain letters, numbers, hyphens, and underscores"
            )

        # Cannot start or end with hyphen or underscore
        if value.startswith(("-", "_")) or value.endswith(("-", "_")):
            raise ValidationError(
                "Username cannot start or end with hyphen or underscore"
            )


class Slug(ValueObject):
    """Slug value object with validation."""

    def _validate(self, value: str) -> None:
        """Validate slug format."""
        if not value or not isinstance(value, str):
            raise ValidationError("Slug cannot be empty")

        if len(value) < 1:
            raise ValidationError("Slug must be at least 1 character long")

        if len(value) > 63:
            raise ValidationError("Slug too long (max 63 characters)")

        # Slug must be lowercase
        if value != value.lower():
            raise ValidationError("Slug must contain only lowercase letters")

        # Slug can contain lowercase letters, numbers, hyphens
        if not re.match(r"^[a-z0-9-]+$", value):
            raise ValidationError(
                "Slug can only contain lowercase letters, numbers, and hyphens"
            )

        # Cannot start or end with hyphen
        if value.startswith("-") or value.endswith("-"):
            raise ValidationError("Slug cannot start or end with hyphen")

        # Cannot contain consecutive hyphens
        if "--" in value:
            raise ValidationError("Slug cannot contain consecutive hyphens")


class Version(ValueObject):
    """Version value object with semantic versioning validation."""

    def _validate(self, value: str) -> None:
        """Validate semantic version format."""
        if not value or not isinstance(value, str):
            raise ValidationError("Version cannot be empty")

        # Basic semantic version pattern (major.minor.patch)
        version_pattern = r"^(\d+)\.(\d+)\.(\d+)(?:-([a-zA-Z0-9\-]+(?:\.[a-zA-Z0-9\-]+)*))?(?:\+([a-zA-Z0-9\-]+(?:\.[a-zA-Z0-9\-]+)*))?$"
        if not re.match(version_pattern, value):
            raise ValidationError(
                "Invalid version format (must follow semantic versioning: major.minor.patch)"
            )
