"""``hub.auth``: signing in and out. Satellite tokens for Spaces are minted, cached and refreshed
inside the transport; nothing here is needed for them."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .errors import AuthError, NotLoggedIn
from .models import AuthMethod, Identity, Money

if TYPE_CHECKING:  # pragma: no cover
    from .hub import AsyncHub


class AuthNamespace:
    """Sign in with a password, a personal access token, or Google. Reached as ``hub.auth``.

    Discovery and free sources work without signing in; paid sources, wallets and MPP need a user."""

    def __init__(self, hub: "AsyncHub") -> None:
        self._hub = hub

    async def _set(self, user: dict[str, Any], method: AuthMethod) -> Identity:
        me = Identity(username=user["username"], email=user["email"], auth=method,
                      hub_wallet_balance=Money.of(user.get("hub_wallet", 0)))
        self._hub.me = me
        self._hub._tokens.clear()        # guest tokens are no longer the right identity
        return me

    async def login(self, *, username: str, password: str) -> Identity:
        """Sign in with a username and password.

        Args:
            username: Your Hub username.
            password: Your Hub password.

        Returns:
            Your ``Identity``.

        Raises:
            AuthError: When the Hub rejects the credentials."""
        try:
            user = await self._hub._t.hub_login("password", username=username, password=password)
        except PermissionError as e:
            raise AuthError(f"Hub rejected the password for {username!r}: {e}", who="hub") from None
        return await self._set(user, AuthMethod.PASSWORD)

    async def login_with_token(self, token: str) -> Identity:
        """Sign in with a personal access token created in the Hub's settings. The headless path.

        Args:
            token: The token.

        Returns:
            Your ``Identity``.

        Raises:
            AuthError: When the Hub does not know the token."""
        try:
            user = await self._hub._t.hub_login("token", token=token)
        except PermissionError as e:
            raise AuthError(f"Hub rejected the personal access token: {e}", who="hub") from None
        return await self._set(user, AuthMethod.TOKEN)

    async def login_with_google(self) -> Identity:
        """Sign in with Google. Opens the browser and returns once the Hub confirms.

        Returns:
            Your ``Identity``."""
        user = await self._hub._t.hub_login("google")
        return await self._set(user, AuthMethod.GOOGLE)

    async def whoami(self) -> Identity:
        """Who is signed in, with the Hub wallet balance refreshed.

        Returns:
            Your ``Identity``.

        Raises:
            NotLoggedIn: When nobody is signed in."""
        if self._hub.me is None:
            raise NotLoggedIn()
        bal = await self._hub._t.hub_wallet_balance()
        self._hub.me = self._hub.me.model_copy(update={"hub_wallet_balance": Money.of(bal)})
        return self._hub.me

    async def logout(self) -> None:
        """Sign out and forget every cached token."""
        await self._hub._t.hub_logout()
        self._hub.me = None
        self._hub._tokens.clear()
