"""Tests for domain package initialization."""


def test_domain_package_imports():
    """Test that domain package imports work correctly."""
    from syfthub.domain import DomainException, Email, Slug, Username

    # Test that imports are available
    assert DomainException is not None
    assert Email is not None
    assert Username is not None
    assert Slug is not None


def test_domain_package_all():
    """Test that __all__ exports work correctly."""
    import syfthub.domain as domain

    # Test __all__ contents
    expected_exports = ["DomainException", "Email", "Username", "Slug"]

    for export in expected_exports:
        assert hasattr(domain, export)
        assert export in domain.__all__


def test_domain_imports_functional():
    """Test that imported classes work functionally."""
    from syfthub.domain import DomainException, Email, Slug, Username

    # Test that we can actually use the imported classes
    exception = DomainException("test")
    assert str(exception) == "test"

    email = Email("test@example.com")
    assert email.value == "test@example.com"

    username = Username("testuser")
    assert username.value == "testuser"

    slug = Slug("test-slug")
    assert slug.value == "test-slug"
