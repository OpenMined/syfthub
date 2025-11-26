"""Tests for domain value objects."""

import pytest

from syfthub.domain.exceptions import ValidationError
from syfthub.domain.value_objects import Email, Slug, Username, ValueObject, Version


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


class TestEmail:
    """Test Email value object."""

    def test_valid_email_creation(self):
        """Test creating valid email."""
        email = Email("user@example.com")

        assert email.value == "user@example.com"
        assert str(email) == "user@example.com"

    def test_valid_email_variations(self):
        """Test various valid email formats."""
        valid_emails = [
            "simple@example.com",
            "test.email@example.com",
            "test+tag@example.com",
            "user123@example-site.com",
            "user_name@example.co.uk",
            "a@b.co",
        ]

        for email_str in valid_emails:
            email = Email(email_str)
            assert email.value == email_str

    def test_empty_email_validation(self):
        """Test empty email validation."""
        with pytest.raises(ValidationError, match="Email cannot be empty"):
            Email("")

        with pytest.raises(ValidationError, match="Email cannot be empty"):
            Email(None)

    def test_non_string_email_validation(self):
        """Test non-string email validation."""
        with pytest.raises(ValidationError, match="Email cannot be empty"):
            Email(123)

    def test_invalid_email_format(self):
        """Test invalid email format validation."""
        invalid_emails = [
            "invalid",
            "@example.com",
            "user@",
            "user@@example.com",
            "user@example",
            "user@.com",
            "user name@example.com",
        ]

        for invalid_email in invalid_emails:
            with pytest.raises(ValidationError, match="Invalid email format"):
                Email(invalid_email)

    def test_email_too_long(self):
        """Test email length validation."""
        long_email = "a" * 250 + "@example.com"  # Over 255 chars

        with pytest.raises(ValidationError, match="Email too long"):
            Email(long_email)


class TestUsername:
    """Test Username value object."""

    def test_valid_username_creation(self):
        """Test creating valid username."""
        username = Username("validuser")

        assert username.value == "validuser"
        assert str(username) == "validuser"

    def test_valid_username_variations(self):
        """Test various valid username formats."""
        valid_usernames = [
            "abc",
            "user123",
            "test_user",
            "test-user",
            "User_Name123",
            "a" * 50,  # Max length
        ]

        for username_str in valid_usernames:
            username = Username(username_str)
            assert username.value == username_str

    def test_empty_username_validation(self):
        """Test empty username validation."""
        with pytest.raises(ValidationError, match="Username cannot be empty"):
            Username("")

        with pytest.raises(ValidationError, match="Username cannot be empty"):
            Username(None)

    def test_non_string_username_validation(self):
        """Test non-string username validation."""
        with pytest.raises(ValidationError, match="Username cannot be empty"):
            Username(123)

    def test_username_too_short(self):
        """Test username minimum length validation."""
        with pytest.raises(
            ValidationError, match="Username must be at least 3 characters long"
        ):
            Username("ab")

    def test_username_too_long(self):
        """Test username maximum length validation."""
        long_username = "a" * 51  # Over 50 chars

        with pytest.raises(ValidationError, match="Username too long"):
            Username(long_username)

    def test_invalid_username_characters(self):
        """Test invalid username characters."""
        invalid_usernames = [
            "user@name",
            "user name",
            "user.name",
            "user+name",
            "user#name",
            "user%name",
        ]

        for invalid_username in invalid_usernames:
            with pytest.raises(ValidationError, match="Username can only contain"):
                Username(invalid_username)

    def test_username_start_end_validation(self):
        """Test username cannot start/end with hyphen or underscore."""
        invalid_usernames = ["-username", "_username", "username-", "username_"]

        for invalid_username in invalid_usernames:
            with pytest.raises(ValidationError, match="Username cannot start or end"):
                Username(invalid_username)


class TestSlug:
    """Test Slug value object."""

    def test_valid_slug_creation(self):
        """Test creating valid slug."""
        slug = Slug("valid-slug")

        assert slug.value == "valid-slug"
        assert str(slug) == "valid-slug"

    def test_valid_slug_variations(self):
        """Test various valid slug formats."""
        valid_slugs = [
            "a",
            "abc",
            "test-slug",
            "slug123",
            "test-123",
            "a" * 63,  # Max length
        ]

        for slug_str in valid_slugs:
            slug = Slug(slug_str)
            assert slug.value == slug_str

    def test_empty_slug_validation(self):
        """Test empty slug validation."""
        with pytest.raises(ValidationError, match="Slug cannot be empty"):
            Slug("")

        with pytest.raises(ValidationError, match="Slug cannot be empty"):
            Slug(None)

    def test_non_string_slug_validation(self):
        """Test non-string slug validation."""
        with pytest.raises(ValidationError, match="Slug cannot be empty"):
            Slug(123)

    def test_slug_too_long(self):
        """Test slug maximum length validation."""
        long_slug = "a" * 64  # Over 63 chars

        with pytest.raises(ValidationError, match="Slug too long"):
            Slug(long_slug)

    def test_slug_uppercase_validation(self):
        """Test slug must be lowercase."""
        with pytest.raises(
            ValidationError, match="Slug must contain only lowercase letters"
        ):
            Slug("Test-Slug")

    def test_invalid_slug_characters(self):
        """Test invalid slug characters."""
        invalid_slugs = [
            "slug_with_underscore",
            "slug with spaces",
            "slug@special",
            "slug.dot",
            "slug+plus",
        ]

        for invalid_slug in invalid_slugs:
            with pytest.raises(ValidationError, match="Slug can only contain"):
                Slug(invalid_slug)

    def test_slug_start_end_hyphen(self):
        """Test slug cannot start/end with hyphen."""
        invalid_slugs = ["-slug", "slug-"]

        for invalid_slug in invalid_slugs:
            with pytest.raises(
                ValidationError, match="Slug cannot start or end with hyphen"
            ):
                Slug(invalid_slug)

    def test_slug_consecutive_hyphens(self):
        """Test slug cannot contain consecutive hyphens."""
        with pytest.raises(
            ValidationError, match="Slug cannot contain consecutive hyphens"
        ):
            Slug("slug--with--double")


class TestVersion:
    """Test Version value object."""

    def test_valid_version_creation(self):
        """Test creating valid version."""
        version = Version("1.2.3")

        assert version.value == "1.2.3"
        assert str(version) == "1.2.3"

    def test_valid_version_variations(self):
        """Test various valid version formats."""
        valid_versions = [
            "0.0.1",
            "1.0.0",
            "10.20.30",
            "1.2.3-alpha",
            "1.2.3-alpha.1",
            "1.2.3-beta.2.3",
            "1.2.3+build.1",
            "1.2.3-alpha+build.1",
        ]

        for version_str in valid_versions:
            version = Version(version_str)
            assert version.value == version_str

    def test_empty_version_validation(self):
        """Test empty version validation."""
        with pytest.raises(ValidationError, match="Version cannot be empty"):
            Version("")

        with pytest.raises(ValidationError, match="Version cannot be empty"):
            Version(None)

    def test_non_string_version_validation(self):
        """Test non-string version validation."""
        with pytest.raises(ValidationError, match="Version cannot be empty"):
            Version(123)

    def test_invalid_version_format(self):
        """Test invalid version format validation."""
        invalid_versions = [
            "1.2",
            "1",
            "1.2.3.4",
            "v1.2.3",
            "1.2.3-",
            "1.2.3+",
            "a.b.c",
            "1.2.x",
        ]

        for invalid_version in invalid_versions:
            with pytest.raises(ValidationError, match="Invalid version format"):
                Version(invalid_version)
