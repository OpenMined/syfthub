"""Per-host circuit breaker.

After ``failures`` consecutive failures a host is open for ``cooldown`` seconds: pre-flight holds
its rows with ``CIRCUIT_OPEN`` and nothing is sent. Once the cooldown has passed the host is
half-open: the next execute sends one probe first, and the rest of that host's rows only after
the probe comes back without a failure. Reading the state never changes it.
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


class Breakers(BaseModel):
    settings: CircuitBreaker = CircuitBreaker()
    _states: dict[str, _State] = PrivateAttr(default_factory=dict)

    def _state(self, host: str) -> _State:
        return self._states.setdefault(host, _State())

    def _remaining(self, host: str) -> float | None:
        st = self._state(host)
        if st.opened_at is None:
            return None
        return self.settings.cooldown - (time.monotonic() - st.opened_at)

    def reopens_at(self, host: str) -> datetime | None:
        """When an open host may be probed again, or None when requests may be sent."""
        remaining = self._remaining(host)
        if remaining is None or remaining <= 0:
            return None
        return datetime.now(timezone.utc) + timedelta(seconds=remaining)

    def is_open(self, host: str) -> bool:
        return self.reopens_at(host) is not None

    def half_open(self, host: str) -> bool:
        """Open earlier, cooldown elapsed, no verdict yet: send one probe before the rest."""
        remaining = self._remaining(host)
        return remaining is not None and remaining <= 0

    def success(self, host: str) -> None:
        self._states[host] = _State()

    def failure(self, host: str, *, connection: bool = False) -> None:
        """Count a failure. A ``connection`` failure (timeout, refused, DNS) means the host is
        down, so it opens the circuit at once; a 5xx counts toward ``settings.failures``."""
        st = self._state(host)
        st.failures += 1
        if connection or st.opened_at is not None or st.failures >= self.settings.failures:
            st.opened_at = time.monotonic()
