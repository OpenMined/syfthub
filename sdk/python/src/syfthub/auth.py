"""Login flows, the session's Hub tokens, satellite tokens for Spaces, and ``Identity``."""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING, Any
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr

from .errors import AuthError, ConfigurationError
from .models.enums import AuthMethod
from .models.session import Identity

if TYPE_CHECKING:
    from ._api.hub import HubApi


class Session(BaseModel):
    """The Hub access and refresh tokens, plus the credentials to re-mint them."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    access_token: str | None = Field(default=None, repr=False)
    refresh_token: str | None = Field(default=None, repr=False)
    username: str | None = None
    password: str | None = Field(default=None, repr=False)
    _api: Any = PrivateAttr(default=None)
    _lock: asyncio.Lock | None = PrivateAttr(default=None)

    def attach(self, api: HubApi) -> None:
        self._api = api

    @property
    def authenticated(self) -> bool:
        return self.access_token is not None

    def headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.access_token}"} if self.access_token else {}

    async def renew(self) -> bool:
        """One attempt to get a fresh access token: refresh, else re-login with the stored
        password. Returns False when neither is possible.

        Safe under concurrency: callers that queued behind a renewal in progress see the token
        already rotated and return without renewing again. The refresh and login calls go to the
        transport directly, never back through the 401 handler, so the lock is never re-entered.
        """
        api: HubApi | None = self._api
        if api is None:
            return False
        if self._lock is None:
            self._lock = asyncio.Lock()
        seen = self.access_token
        async with self._lock:
            if self.access_token != seen:
                return True
            if self.refresh_token:
                body = await api.refresh(self.refresh_token)
                if body and body.get("access_token"):
                    self.access_token = str(body["access_token"])
                    self.refresh_token = str(body.get("refresh_token") or self.refresh_token)
                    return True
            if self.username and self.password:
                try:
                    body = await api.login(self.username, self.password)
                except AuthError:
                    return False
                self.access_token = str(body["access_token"])
                self.refresh_token = str(body.get("refresh_token") or "")
                return True
        return False


class _Cached(BaseModel):
    token: str
    expires_at: float


class TokenCache:
    """Satellite tokens keyed by ``(owner, resource)``, refreshed at 80% of their lifetime."""

    def __init__(self, api: HubApi) -> None:
        self.api = api
        self._tokens: dict[tuple[str, str], _Cached] = {}
        self._locks: dict[tuple[str, str], asyncio.Lock] = {}

    @staticmethod
    def resource_of(url: str) -> str:
        parts = urlsplit(url)
        return f"{parts.scheme}://{parts.netloc}" if parts.scheme and parts.netloc else url

    async def get(self, owner: str, url: str) -> str:
        key = (owner, self.resource_of(url))
        cached = self._tokens.get(key)
        if cached and cached.expires_at > time.monotonic():
            return cached.token
        lock = self._locks.setdefault(key, asyncio.Lock())
        async with lock:
            cached = self._tokens.get(key)
            if cached and cached.expires_at > time.monotonic():
                return cached.token
            token, expires_in = await self.api.satellite_token(owner, key[1])
            self._tokens[key] = _Cached(
                token=token, expires_at=time.monotonic() + max(1.0, expires_in * 0.8)
            )
            return token

    def clear(self) -> None:
        self._tokens.clear()


class AuthNamespace:
    """``hub.auth``: login and identity. ``hub.login`` and ``hub.me`` are aliases."""

    def __init__(self, api: HubApi, session: Session) -> None:
        self._api = api
        self._session = session
        self.me: Identity | None = None

    async def login(
        self,
        username: str | None = None,
        password: str | None = None,
        *,
        token: str | None = None,
    ) -> Identity:
        if token is not None:
            if username or password:
                raise ConfigurationError("pass either token= or username/password, not both")
            self._session.access_token = token
            self._session.refresh_token = None
            self._session.username = self._session.password = None
            identity = await self._whoami(AuthMethod.TOKEN)
        elif username and password:
            body = await self._api.login(username, password)
            self._session.access_token = str(body["access_token"])
            self._session.refresh_token = str(body.get("refresh_token") or "")
            self._session.username, self._session.password = username, password
            identity = await self._whoami(AuthMethod.PASSWORD)
        else:
            raise ConfigurationError("login needs username and password, or token=")
        self.me = identity
        return identity

    async def whoami(self) -> Identity:
        method = AuthMethod.PASSWORD if self._session.password else AuthMethod.TOKEN
        self.me = await self._whoami(method)
        return self.me

    async def _whoami(self, method: AuthMethod) -> Identity:
        body: dict[str, Any] = await self._api.me()
        return Identity(
            username=str(body.get("username", "")), email=str(body.get("email", "")), auth=method
        )
