"""Tests for the satellite domain types."""

import dataclasses
import uuid
from datetime import datetime, timezone

import pytest

from syfthub.domain.base_url import BaseUrl
from syfthub.domain.satellite import SatelliteKind, SatelliteRef


def _ref(**overrides) -> SatelliteRef:
    """Build a SatelliteRef with sensible defaults."""
    defaults = {
        "id": 1,
        "public_id": uuid.uuid4(),
        "user_id": 7,
        "kind": SatelliteKind.SPACE,
        "base_url": BaseUrl("https://space.example.com"),
        "created_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
        "last_seen_at": None,
    }
    return SatelliteRef(**{**defaults, **overrides})


class TestSatelliteKind:
    """The kind is a string enum, matching every other enum in this schema."""

    def test_values(self):
        """Test the wire values, which are what the column stores."""
        assert SatelliteKind.SPACE.value == "space"
        assert SatelliteKind.STATION.value == "station"

    def test_is_a_str(self):
        """Test that the enum is str-comparable, as the codebase expects."""
        assert SatelliteKind.SPACE == "space"

    def test_round_trips_a_stored_value(self):
        """Test that a stored value reconstructs its member."""
        for kind in SatelliteKind:
            assert SatelliteKind(kind.value) is kind

    def test_rejects_an_unknown_value(self):
        """Test that a corrupt stored kind raises rather than coercing.

        ValueError, not a domain error: the column is only ever written from
        this enum, so a bad value is corrupt data and a 500 is honest.
        """
        with pytest.raises(ValueError):
            SatelliteKind("planet")

    def test_is_case_sensitive(self):
        """Test that casing is not silently coerced."""
        with pytest.raises(ValueError):
            SatelliteKind("Space")


class TestSatelliteRef:
    """The reference is immutable and carries both identifiers."""

    def test_is_frozen(self):
        """Test that a resolved satellite cannot be mutated in place."""
        ref = _ref()
        with pytest.raises(dataclasses.FrozenInstanceError):
            ref.base_url = None

    def test_carries_both_identifiers(self):
        """Test that the internal key and exposed identifier are distinct."""
        ref = _ref(id=42)
        assert ref.id == 42
        assert isinstance(ref.public_id, uuid.UUID)

    def test_base_url_is_optional(self):
        """Test a satellite registered before it first reported in."""
        assert _ref(base_url=None).base_url is None

    def test_equality_is_by_value(self):
        """Test that two refs with the same fields are equal."""
        pid = uuid.uuid4()
        assert _ref(public_id=pid) == _ref(public_id=pid)
        assert _ref(public_id=pid) != _ref(public_id=uuid.uuid4())

    def test_is_hashable(self):
        """Test that frozen buys hashability, which dedup relies on."""
        pid = uuid.uuid4()
        assert len({_ref(public_id=pid), _ref(public_id=pid)}) == 1
