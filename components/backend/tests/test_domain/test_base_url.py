"""Tests for the BaseUrl value object.

The property that matters: any two spellings of one origin canonicalise to the
same value and compare equal. Resolution by origin rests on it.
"""

import pytest

from syfthub.domain.base_url import (
    MAX_BASE_URL_LENGTH,
    TUNNELING_PREFIX,
    BaseUrl,
    normalize_base_url,
)
from syfthub.domain.exceptions import ValidationError


class TestNormalization:
    """Distinct spellings of one origin must canonicalise identically."""

    @pytest.mark.parametrize(
        "raw,expected",
        [
            # Already canonical.
            ("https://api.example.com", "https://api.example.com"),
            # Case: schemes and hosts are case-insensitive.
            ("HTTPS://API.Example.COM", "https://api.example.com"),
            ("Http://Host.io", "http://host.io"),
            # Surrounding whitespace, which arrives from config files and forms.
            ("  https://api.example.com  ", "https://api.example.com"),
            ("\thttps://api.example.com\n", "https://api.example.com"),
            # Trailing slashes.
            ("https://api.example.com/", "https://api.example.com"),
            ("https://api.example.com///", "https://api.example.com"),
            # Default ports carry no information and must not distinguish.
            ("https://api.example.com:443", "https://api.example.com"),
            ("http://api.example.com:80", "http://api.example.com"),
            # Non-default ports do, and must survive.
            ("https://api.example.com:8443", "https://api.example.com:8443"),
            ("http://192.168.1.1:8080", "http://192.168.1.1:8080"),
            # An origin has no path, query, or fragment.
            ("https://api.example.com/v1", "https://api.example.com"),
            ("https://api.example.com/v1/deep/path", "https://api.example.com"),
            ("https://api.example.com?a=b", "https://api.example.com"),
            ("https://api.example.com#frag", "https://api.example.com"),
            ("https://api.example.com:8443/v1?a=b#c", "https://api.example.com:8443"),
            # Everything at once.
            ("  HTTPS://API.Example.COM:443/v1/  ", "https://api.example.com"),
        ],
    )
    def test_canonicalises(self, raw, expected):
        """Test that each spelling reduces to the canonical origin."""
        assert normalize_base_url(raw) == expected
        assert BaseUrl(raw).value == expected

    def test_default_port_only_stripped_for_its_own_scheme(self):
        """Test that :443 on http is a real, distinguishing port."""
        assert normalize_base_url("http://host.io:443") == "http://host.io:443"
        assert normalize_base_url("https://host.io:80") == "https://host.io:80"


class TestTunneling:
    """Tunneling pseudo-URLs are routes, not origins, and pass through."""

    def test_passes_through(self):
        """Test that a tunneling address is preserved verbatim."""
        assert normalize_base_url("tunneling:alice") == "tunneling:alice"

    def test_whitespace_still_stripped(self):
        """Test that surrounding whitespace is still removed."""
        assert normalize_base_url("  tunneling:alice  ") == "tunneling:alice"

    def test_case_preserved(self):
        """Test that a tunneling username is not lower-cased (it is a username,
        not a hostname)."""
        assert normalize_base_url("tunneling:Alice") == "tunneling:Alice"

    def test_is_tunneling_flag(self):
        """Test that BaseUrl reports which kind of address it holds."""
        assert BaseUrl("tunneling:alice").is_tunneling is True
        assert BaseUrl("https://host.io").is_tunneling is False

    def test_prefix_is_the_shared_constant(self):
        """Test that the prefix is the one the rest of the codebase uses."""
        assert TUNNELING_PREFIX == "tunneling:"
        assert BaseUrl(f"{TUNNELING_PREFIX}bob").value == "tunneling:bob"


class TestRejection:
    """Anything that is not a usable origin must fail loudly, not silently."""

    @pytest.mark.parametrize(
        "raw,reason",
        [
            ("", "empty"),
            ("   ", "whitespace only"),
            ("host.example.com", "no scheme"),
            ("//host.example.com", "no scheme"),
            ("ftp://host.io", "unsupported scheme"),
            ("file:///etc/passwd", "unsupported scheme"),
            ("https://", "no host"),
            ("https://:8080", "no host"),
            ("https://host.io:notaport", "unparseable port"),
        ],
    )
    def test_rejects(self, raw, reason):
        """Test that unusable input raises rather than being coerced."""
        with pytest.raises(ValidationError):
            normalize_base_url(raw)
        with pytest.raises(ValidationError):
            BaseUrl(raw)

    def test_rejects_embedded_credentials(self):
        """Test that userinfo is refused; the URL builder would leak it."""
        with pytest.raises(ValidationError, match="credentials"):
            BaseUrl("https://user:secret@host.io")
        with pytest.raises(ValidationError, match="credentials"):
            BaseUrl("https://user@host.io")

    def test_rejects_over_long_origin(self):
        """Test that the column width is guarded in the domain."""
        too_long = "https://" + ("a" * MAX_BASE_URL_LENGTH) + ".io"
        with pytest.raises(ValidationError, match="at most"):
            BaseUrl(too_long)

    def test_rejects_over_long_tunneling_address(self):
        """Test that the passthrough branch is length-bounded too."""
        with pytest.raises(ValidationError, match="at most"):
            BaseUrl(TUNNELING_PREFIX + "a" * MAX_BASE_URL_LENGTH)

    def test_error_is_a_domain_validation_error(self):
        """Test that rejection surfaces as HTTP 422, not 500."""
        with pytest.raises(ValidationError) as exc:
            BaseUrl("nonsense")
        assert exc.value.error_code == "VALIDATION_ERROR"


class TestValueSemantics:
    """Equality and hashing are what make an origin usable as a lookup key."""

    def test_equal_across_spellings(self):
        """Test that differently-spelled identical origins compare equal."""
        assert BaseUrl("https://Host.io/") == BaseUrl("https://host.io:443")
        assert BaseUrl("  HTTP://Host.IO:80/v1  ") == BaseUrl("http://host.io")

    def test_distinct_origins_are_not_equal(self):
        """Test that a differing scheme, host, or port distinguishes."""
        assert BaseUrl("https://host.io") != BaseUrl("http://host.io")
        assert BaseUrl("https://host.io") != BaseUrl("https://other.io")
        assert BaseUrl("https://host.io") != BaseUrl("https://host.io:8443")

    def test_hashes_alike(self):
        """Test that equal origins collapse in a set, as the unique index needs."""
        urls = {
            BaseUrl("https://Host.io/"),
            BaseUrl("https://host.io:443"),
            BaseUrl("https://host.io"),
        }
        assert len(urls) == 1

    def test_not_equal_to_a_bare_string(self):
        """Test that a BaseUrl is not interchangeable with its own string."""
        assert BaseUrl("https://host.io") != "https://host.io"

    def test_str_and_repr(self):
        """Test the string forms inherited from ValueObject."""
        url = BaseUrl("https://Host.io/")
        assert str(url) == "https://host.io"
        assert repr(url) == "BaseUrl('https://host.io')"

    def test_value_is_typed_str(self):
        """Test that .value narrows ValueObject's Any to str."""
        assert isinstance(BaseUrl("https://host.io").value, str)
