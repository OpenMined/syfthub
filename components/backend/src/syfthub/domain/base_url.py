"""``BaseUrl`` — a satellite's normalised origin.

Normalising in the constructor, not in a helper, is deliberate: origins are both
stored and compared, so one caller forgetting to normalise would make
``https://Host.example.com/`` and ``https://host.example.com`` two satellites for
one host. Holding a ``BaseUrl`` *is* holding a canonical origin.

Paths are dropped: they live in ``connection.config.url`` and are joined on read
by :mod:`syfthub.core.url_builder`.
"""

from __future__ import annotations

from urllib.parse import urlsplit

from syfthub.domain.exceptions import ValidationError
from syfthub.domain.value_objects import ValueObject

# Pseudo-URL prefix for NAT traversal over NATS pub/sub rather than HTTP. An
# addressing rule, so the domain owns it; core.url_builder and schemas.user
# import it from here.
TUNNELING_PREFIX = "tunneling:"

# Ports that must not be allowed to distinguish two identical origins.
_DEFAULT_PORTS = {"http": 80, "https": 443}

_ALLOWED_SCHEMES = frozenset(_DEFAULT_PORTS)

# Width of satellites.base_url.
MAX_BASE_URL_LENGTH = 500


def normalize_base_url(value: str) -> str:
    """Reduce a URL to its canonical origin.

    Strips whitespace, lower-cases scheme and host, drops default ports and
    path/query/fragment. ``tunneling:`` values pass through.

    Raises:
        ValidationError: Empty, over-long, non-http(s), credential-bearing,
            host-less, or bad port.
    """
    raw = value.strip()
    if not raw:
        raise ValidationError("Base URL must not be empty")

    if raw.startswith(TUNNELING_PREFIX):
        _reject_if_too_long(raw)
        return raw

    if "://" not in raw:
        raise ValidationError(
            f"Base URL must include a scheme, e.g. https://{raw.split('/')[0]}"
        )

    parts = urlsplit(raw)

    scheme = parts.scheme.lower()
    if scheme not in _ALLOWED_SCHEMES:
        allowed = ", ".join(sorted(_ALLOWED_SCHEMES))
        raise ValidationError(f"Base URL scheme must be one of: {allowed}")

    # The URL builder replays stored origins into links given to third parties,
    # so credentials in one would leak.
    if parts.username is not None or parts.password is not None:
        raise ValidationError("Base URL must not embed credentials")

    hostname = parts.hostname
    if not hostname:
        raise ValidationError("Base URL must include a host")

    try:
        port = parts.port
    except ValueError as exc:
        # urlsplit defers port parsing to attribute access.
        raise ValidationError("Base URL has an invalid port") from exc

    origin = f"{scheme}://{hostname}"
    if port is not None and port != _DEFAULT_PORTS[scheme]:
        origin = f"{origin}:{port}"

    _reject_if_too_long(origin)
    return origin


def _reject_if_too_long(value: str) -> None:
    """Guard the column width in the domain, not at the driver."""
    if len(value) > MAX_BASE_URL_LENGTH:
        raise ValidationError(
            f"Base URL must be at most {MAX_BASE_URL_LENGTH} characters"
        )


class BaseUrl(ValueObject):
    """A satellite's origin, normalised on construction.

    Equal across spellings, so it works as a resolution key:
    ``BaseUrl("https://H.io/") == BaseUrl("https://h.io:443")``.

    Raises:
        ValidationError: Not a usable origin. Mapped to HTTP 422.
    """

    def __init__(self, value: str):
        """Normalise, validate, then store."""
        super().__init__(normalize_base_url(value))

    @property
    def value(self) -> str:
        """The canonical origin."""
        return str(self._value)

    @property
    def is_tunneling(self) -> bool:
        """Whether this is a ``tunneling:`` route rather than an origin."""
        return self.value.startswith(TUNNELING_PREFIX)


__all__ = [
    "MAX_BASE_URL_LENGTH",
    "TUNNELING_PREFIX",
    "BaseUrl",
    "normalize_base_url",
]
