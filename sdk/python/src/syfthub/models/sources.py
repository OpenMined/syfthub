"""``Source``, its policies and pricing, and ``SourceList``.

A Hub endpoint is a source in the SDK. Field names follow the Hub's ``EndpointPublicResponse``;
``raw`` keeps the verbatim body.
"""

from __future__ import annotations

from collections.abc import Iterator
from difflib import SequenceMatcher
from fnmatch import fnmatchcase
from typing import Any

from pydantic import Field

from .base import Frozen
from .enums import PAYMENT_POLICY_TYPES, Health, PolicyType, PriceUnit, Rail, SourceType
from .money import Bundle, Money

_DEFAULT_CURRENCY: dict[str, str] = {Rail.XENDIT.value: "IDR"}


class Policy(Frozen):
    """One entry of ``EndpointPublicResponse.policies[]``. ``type`` is the Hub's string; unknown
    types still parse, and ``known`` names the ones the SDK understands."""

    type: str
    config: dict[str, Any] = Field(default_factory=dict)
    version: str = "1.0"
    enabled: bool = True
    description: str = ""

    @property
    def known(self) -> PolicyType | None:
        try:
            return PolicyType(self.type)
        except ValueError:
            return None

    @property
    def is_payment(self) -> bool:
        return self.type in PAYMENT_POLICY_TYPES


class Connection(Frozen):
    """One entry of ``EndpointPublicResponse.connect[]``."""

    type: str
    config: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True
    description: str = ""

    @property
    def url(self) -> str | None:
        value = self.config.get("url") or self.config.get("base_url")
        return value if isinstance(value, str) and value else None


class Price(Frozen):
    """One payment policy's price: an amount per request or per document."""

    amount: Money
    unit: PriceUnit = PriceUnit.REQUEST
    policy_type: str = ""


def matches_patterns(email: str, patterns: tuple[str, ...]) -> str | None:
    """The first glob pattern that matches ``email`` (case-insensitive), or None."""
    needle = email.strip().lower()
    for pattern in patterns:
        if fnmatchcase(needle, pattern.strip().lower()):
            return pattern
    return None


class Pricing(Frozen):
    """Read off a source's payment policies; nothing added.

    An endpoint may carry a per-request and a per-document price on the same wallet, so
    ``prices`` holds every enabled payment policy and ``estimate`` sums them. ``price`` and
    ``unit`` are the first one, for display.
    """

    rail: Rail = Rail.FREE
    prices: tuple[Price, ...] = ()
    currency: str = "USD"
    applied_to: tuple[str, ...] = ()
    wallet_id: str | None = None
    wallet_owner: str | None = None
    bundles: tuple[Bundle, ...] = ()
    payment_url: str | None = None
    credits_url: str | None = None
    invoices_url: str | None = None

    @property
    def price(self) -> Money:
        return self.prices[0].amount if self.prices else Money.zero(self.currency)

    @property
    def unit(self) -> PriceUnit:
        return self.prices[0].unit if self.prices else PriceUnit.REQUEST

    @property
    def free(self) -> bool:
        return self.rail is Rail.FREE or not any(p.amount.positive for p in self.prices)

    def applies_to(self, email: str | None) -> bool:
        """Whether the caller is charged: ``applied_to`` empty or ``*`` means everyone."""
        if not self.applied_to or "*" in self.applied_to:
            return True
        return email is not None and matches_patterns(email, self.applied_to) is not None

    def estimate(self, limit: int) -> Money:
        """Maximum cost of one query: per-request prices once, per-document prices ``limit`` times."""
        total = Money.zero(self.currency)
        for p in self.prices:
            total = total + (p.amount * (limit if p.unit is PriceUnit.DOCUMENT else 1))
        return total


class Access(Frozen):
    """What the source's access policies say about one caller."""

    allowed: bool = True
    rule: str | None = None


def _str(config: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = config.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def _number(config: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = config.get(key)
        if isinstance(value, (int, float, str)) and not isinstance(value, bool):
            return value
    return None


def _rail_of(policy_type: str) -> Rail | None:
    """``stripe`` on the Hub wire; ``stripe_per_request`` on a Space. Both name the rail."""
    head = policy_type.split("_per_", 1)[0]
    try:
        return Rail(head)
    except ValueError:
        return None


def _price(policy: Policy, currency: str) -> Price:
    config = policy.config
    raw = _number(config, "price", "price_per_unit", "price_per_request")
    unit_type = _str(config, "unit_type") or (
        "document" if policy.type.endswith("_per_document") else "request"
    )
    return Price(
        amount=Money.of(raw, currency) if raw is not None else Money.zero(currency),
        unit=PriceUnit.DOCUMENT if unit_type == "document" else PriceUnit.REQUEST,
        policy_type=policy.type,
    )


def pricing_from_policies(policies: tuple[Policy, ...]) -> Pricing | None:
    """Every enabled payment policy folded into one ``Pricing``; None when there is none.

    All payment policies on one endpoint share one wallet, so the wallet fields come from the
    first; the prices are summed by ``estimate``.
    """
    payment = [
        (p, r)
        for p in policies
        if p.enabled and (r := _rail_of(p.type)) is not None and r is not Rail.FREE
    ]
    if not payment:
        return None
    first, rail = payment[0]
    config = first.config
    currency = (_str(config, "currency") or _DEFAULT_CURRENCY.get(rail.value, "USD")).upper()
    bundles: list[Bundle] = []
    for b in config.get("bundles") or ():
        if isinstance(b, dict) and isinstance(b.get("name"), str) and b.get("amount") is not None:
            bundles.append(Bundle(id=b["name"], amount=Money.of(b["amount"], currency)))
    applied = config.get("applied_to") or ()
    return Pricing(
        rail=rail,
        prices=tuple(_price(p, currency) for p, _ in payment),
        currency=currency,
        applied_to=tuple(a for a in applied if isinstance(a, str)),
        wallet_id=_str(config, "wallet_id"),
        wallet_owner=_str(config, "wallet_owner_username", "wallet_owner"),
        bundles=tuple(bundles),
        payment_url=_str(config, "payment_url"),
        credits_url=_str(config, "credits_url"),
        invoices_url=_str(config, "invoices_url"),
    )


def access_for(policies: tuple[Policy, ...], email: str | None) -> Access:
    """Mirror the Space's access policy: denied patterns win; an empty allow list means everyone;
    with several policies the caller passes if any one of them allows."""
    rules = [p for p in policies if p.enabled and p.type == PolicyType.ACCESS.value]
    if not rules:
        return Access()
    if email is None:
        return Access(allowed=False, rule="login required")
    last_rule: str | None = None
    for policy in rules:
        denied = tuple(x for x in policy.config.get("denied_users") or () if isinstance(x, str))
        allowed = tuple(x for x in policy.config.get("allowed_users") or () if isinstance(x, str))
        hit = matches_patterns(email, denied)
        if hit is not None:
            last_rule = f"denied_users: {hit}"
            continue
        if not allowed or matches_patterns(email, allowed) is not None:
            return Access()
        last_rule = f"not in allowed_users: {', '.join(allowed)}"
    return Access(allowed=False, rule=last_rule)


class Source(Frozen):
    """A Hub endpoint. ``path`` (``owner/slug``) is the key used everywhere else."""

    name: str
    slug: str
    type: SourceType
    owner_username: str
    description: str = ""
    version: str = "0.1.0"
    tags: tuple[str, ...] = ()
    stars_count: int = 0
    policies: tuple[Policy, ...] = ()
    connect: tuple[Connection, ...] = ()
    readme: str = ""
    health: Health = Health.UNKNOWN
    raw: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_hub(cls, body: dict[str, Any]) -> Source:
        """Build from an ``EndpointPublicResponse`` body, keeping it verbatim in ``raw``."""
        status = body.get("health_status")
        health = (
            Health(status)
            if status in (Health.HEALTHY.value, Health.UNHEALTHY.value)
            else Health.UNKNOWN
        )
        return cls.model_validate({**body, "health": health, "raw": body})

    @property
    def path(self) -> str:
        return f"{self.owner_username}/{self.slug}"

    @property
    def pricing(self) -> Pricing | None:
        return pricing_from_policies(self.policies)

    @property
    def free(self) -> bool:
        pricing = self.pricing
        return pricing is None or pricing.free

    @property
    def connection(self) -> Connection | None:
        for connection in self.connect:
            if connection.enabled and connection.url:
                return connection
        return None

    @property
    def space_url(self) -> str | None:
        """The Space origin the Hub filled in from the satellite's public URL."""
        connection = self.connection
        return connection.url if connection else None

    @property
    def reachable(self) -> bool:
        """False for tunnelled sources (``tunneling:`` origins go over NATS, not HTTP)."""
        url = self.space_url
        return url is not None and url.startswith(("http://", "https://"))

    @property
    def query_url(self) -> str | None:
        """``{origin}{path}`` with the Space's published path, else the standard query route."""
        connection = self.connection
        if connection is None or connection.url is None:
            return None
        origin = connection.url.rstrip("/")
        path = connection.config.get("path")
        if not isinstance(path, str) or not path:
            path = f"/api/v1/endpoints/{self.slug}/query"
        if origin.endswith(path):
            return origin
        return origin + path

    @property
    def tenant(self) -> str | None:
        connection = self.connection
        value = connection.config.get("tenant_name") if connection else None
        return value if isinstance(value, str) and value else None

    def access(self, email: str | None) -> Access:
        return access_for(self.policies, email)

    def __str__(self) -> str:
        return self.path


def _fuzzy_score(source: Source, text: str) -> float:
    needle = text.strip().lower()
    if not needle:
        return 0.0
    hay_strong = (source.name.lower(), source.slug.lower(), source.path.lower())
    best = max(SequenceMatcher(None, needle, h).ratio() for h in hay_strong)
    if any(needle in h for h in hay_strong):
        best = max(best, 0.9)
    tokens = [t for t in needle.split() if len(t) > 2]
    weak = " ".join((source.description.lower(), " ".join(source.tags).lower()))
    if tokens and all(t in weak for t in tokens):
        best = max(best, 0.7)
    elif tokens and any(t in weak for t in tokens):
        best = max(best, 0.5)
    return best


class SourceList(Frozen):
    """What ``hub.sources.list()`` returns. Every view returns a new list; ``total`` is the Hub's
    count before any local view."""

    items: tuple[Source, ...] = ()
    total: int = 0

    def __iter__(self) -> Iterator[Source]:  # type: ignore[override]
        return iter(self.items)

    def __len__(self) -> int:
        return len(self.items)

    def __getitem__(self, key: int | str) -> Source:
        if isinstance(key, int):
            return self.items[key]
        for source in self.items:
            if source.path == key:
                return source
        raise KeyError(key)

    def __contains__(self, key: object) -> bool:
        if isinstance(key, Source):
            return key in self.items
        return any(s.path == key for s in self.items)

    @property
    def paths(self) -> tuple[str, ...]:
        return tuple(s.path for s in self.items)

    def _view(self, items: list[Source]) -> SourceList:
        return SourceList(items=tuple(items), total=self.total)

    def matching(self, text: str, *, threshold: float = 0.5) -> SourceList:
        """Fuzzy match over name, slug, description and tags; best first."""
        scored = [(s, _fuzzy_score(s, text)) for s in self.items]
        kept = [s for s, score in sorted(scored, key=lambda p: -p[1]) if score >= threshold]
        return self._view(kept)

    def filter(
        self,
        *,
        type: SourceType | str | None = None,
        owner: str | None = None,
        free: bool | None = None,
        tag: str | None = None,
    ) -> SourceList:
        want_type = SourceType(type) if isinstance(type, str) else type
        kept = [
            s
            for s in self.items
            if (want_type is None or s.type is want_type)
            and (owner is None or s.owner_username == owner)
            and (free is None or s.free == free)
            and (tag is None or tag in s.tags)
        ]
        return self._view(kept)

    def pick(self, *paths: str) -> SourceList:
        return self._view([self[p] for p in paths])

    def __add__(self, other: SourceList) -> SourceList:
        seen = set(self.paths)
        extra = [s for s in other.items if s.path not in seen]
        return SourceList(items=self.items + tuple(extra), total=max(self.total, other.total))
