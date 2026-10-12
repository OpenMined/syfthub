"""Per-host circuit breaker.

After ``failures`` consecutive failures a host is open for ``cooldown`` seconds; while open, callers
hold rows with ``CIRCUIT_OPEN`` and send nothing. After the cooldown one probe is allowed; its
success closes the breaker, its failure reopens it.
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit

from pydantic import BaseModel, PrivateAttr

from ..models.session import CircuitBreaker


def host_of(url: str) -> str:
    parts = urlsplit(url)
    return parts.netloc or url


class _State(BaseModel):
    failures: int = 0
    opened_at: float | None = None
    probing: bool = False


class Breakers(BaseModel):
    settings: CircuitBreaker = CircuitBreaker()
    _states: dict[str, _State] = PrivateAttr(default_factory=dict)

    def _state(self, host: str) -> _State:
        return self._states.setdefault(host, _State())

    def reopens_at(self, host: str) -> datetime | None:
        """When an open host closes again, or None when requests may be sent."""
        st = self._state(host)
        if st.opened_at is None:
            return None
        elapsed = time.monotonic() - st.opened_at
        remaining = self.settings.cooldown - elapsed
        if remaining <= 0:
            if not st.probing:
                st.probing = True  # one probe goes through
                return None
            return datetime.now(timezone.utc)
        return datetime.now(timezone.utc) + timedelta(seconds=remaining)

    def is_open(self, host: str) -> bool:
        return self.reopens_at(host) is not None

    def success(self, host: str) -> None:
        self._states[host] = _State()

    def failure(self, host: str) -> None:
        st = self._state(host)
        st.failures += 1
        st.probing = False
        if st.opened_at is not None or st.failures >= self.settings.failures:
            st.opened_at = time.monotonic()
