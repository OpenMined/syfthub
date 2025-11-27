"""Tests for domain value objects."""

import pytest

from syfthub.domain.exceptions import ValidationError
from syfthub.domain.value_objects import ValueObject


class TestValueObject:
    """Test base ValueObject class."""

    class TestValueObjectImpl(ValueObject):
        """Test implementation of ValueObject."""

        def _validate(self, value):
            if not value:
                raise ValidationError("Value cannot be empty")

    def test_value_object_creation(self):
        """Test creating a value object."""
        vo = self.TestValueObjectImpl("test_value")

        assert vo.value == "test_value"
        assert str(vo) == "test_value"
        assert repr(vo) == "TestValueObjectImpl('test_value')"

    def test_value_object_validation_called(self):
        """Test that validation is called during creation."""
        with pytest.raises(ValidationError):
            self.TestValueObjectImpl("")

    def test_value_object_equality(self):
        """Test value object equality comparison."""
        vo1 = self.TestValueObjectImpl("same_value")
        vo2 = self.TestValueObjectImpl("same_value")
        vo3 = self.TestValueObjectImpl("different_value")

        assert vo1 == vo2
        assert vo1 != vo3
        assert vo1 != "same_value"  # Different type
        assert vo1 is not None

    def test_value_object_hash(self):
        """Test value object hashing."""
        vo1 = self.TestValueObjectImpl("hash_test")
        vo2 = self.TestValueObjectImpl("hash_test")

        assert hash(vo1) == hash(vo2)
        assert vo1 in {vo2}  # Can be used in sets
