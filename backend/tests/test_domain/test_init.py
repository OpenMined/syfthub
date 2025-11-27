"""Tests for domain package initialization."""


def test_domain_package_imports():
    """Test that domain package imports work correctly."""
    from syfthub.domain import DomainException, ValidationError, ValueObject

    # Test that imports are available
    assert DomainException is not None
    assert ValidationError is not None
    assert ValueObject is not None


def test_domain_package_all():
    """Test that __all__ exports work correctly."""
    import syfthub.domain as domain

    # Test __all__ contents
    expected_exports = ["DomainException", "ValidationError", "ValueObject"]

    for export in expected_exports:
        assert hasattr(domain, export)
        assert export in domain.__all__


def test_domain_imports_functional():
    """Test that imported classes work functionally."""
    from syfthub.domain import DomainException, ValidationError, ValueObject

    # Test that we can actually use the imported classes
    exception = DomainException("test")
    assert str(exception) == "test"

    validation_error = ValidationError("validation test")
    assert validation_error.error_code == "VALIDATION_ERROR"

    # Test ValueObject can be subclassed
    class TestVO(ValueObject):
        pass

    vo = TestVO("test_value")
    assert vo.value == "test_value"
