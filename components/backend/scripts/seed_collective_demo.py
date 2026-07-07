#!/usr/bin/env python3
"""Seed mock data for the collective pricing + settlement demo.

Creates a buyer user, several publisher users whose endpoints carry per-request
*prepaid* policies (in IDR and USD), plus a free endpoint and a metered (MPP)
endpoint, and groups them all into one collective with two curated shared
endpoints. This gives the frontend enough base data to exercise:

- the estimated-price badge (per-currency sum, e.g. ``4,000 IDR + 0.65 USD``),
- the "Check my accounts" settlement modal (per-publisher prepaid rows +
  the single Hub/MPP wallet row + the "N free" note),
- the chat-style "initiate an invoice" flow for unsettled publishers.

The demo publisher payment/credits URLs are intentionally non-resolving — the
balance fetch fails closed, so every prepaid account renders in the
"needs settlement / initiate invoice" state, which is exactly the flow to
demo. Pricing and member classification come from the backend and need no
external calls.

Usage:
    # from components/backend/
    uv run python scripts/seed_collective_demo.py
    uv run python scripts/seed_collective_demo.py --reset   # wipe + reseed

Log in to the frontend as the buyer (printed at the end) and open the
collective at /c/apac-open-data.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# Make ``syfthub`` importable when run directly from components/backend/.
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from sqlalchemy import inspect, select
from sqlalchemy.orm import Session

from syfthub.auth.security import hash_password
from syfthub.core.config import settings
from syfthub.database.connection import engine
from syfthub.models.collective import (
    CollectiveMemberModel,
    CollectiveModel,
    CollectiveSharedEndpointMemberModel,
    CollectiveSharedEndpointModel,
)
from syfthub.models.endpoint import EndpointModel
from syfthub.models.user import UserModel

# --------------------------------------------------------------------------
# Demo fixture definitions
# --------------------------------------------------------------------------

DEMO_PASSWORD = "demo-password-123"
COLLECTIVE_SLUG = "apac-open-data"
COLLECTIVE_NAME = "APAC Open Data"

# Buyer = the person who logs in, queries the collective, and settles invoices.
BUYER_USERNAME = "demo-buyer"

# Non-resolving demo gateway base; balance fetches fail closed so prepaid rows
# render in the "needs settlement" state.
_GW = "https://pay.demo.syfthub.local"


def _prepaid_policy(
    currency: str, price: float, bundles: list[tuple[str, float]]
) -> dict:
    """Build an enabled Xendit per-request prepaid policy dict."""
    return {
        "type": "xendit",
        "version": "1.0",
        "enabled": True,
        "description": f"Prepaid credits, {currency} per request",
        "config": {
            "payment_url": f"{_GW}/pay",
            "credits_url": f"{_GW}/credits",
            "invoices_url": f"{_GW}/invoices",
            "currency": currency,
            "price": price,
            "unit_type": "request",
            "bundles": [{"name": name, "amount": amount} for name, amount in bundles],
        },
    }


def _mpp_policy(price: float = 0.30, currency: str = "USD") -> dict:
    """Build an enabled MPP policy dict — per-request, settled via the Hub wallet."""
    return {
        "type": "mpp",
        "version": "1.0",
        "enabled": True,
        "description": f"Per-request billing via the Hub (MPP) wallet, {currency}",
        "config": {
            "currency": currency,
            "price": price,
            "unit_type": "request",
            "pricing_mode": "per_call",
        },
    }


# Each publisher owns one endpoint. ``policies`` decides the billing bucket the
# UI sorts it into: prepaid (xendit), metered (transaction/mpp), or free ([]).
PUBLISHERS: list[dict] = [
    {
        "username": "jakarta-data",
        "full_name": "Jakarta Open Data",
        "endpoint_name": "Jakarta Traffic Feed",
        "policies": [
            _prepaid_policy(
                "IDR", 2500, [("Starter 50k", 50_000), ("Pro 200k", 200_000)]
            )
        ],
    },
    {
        "username": "bandung-air",
        "full_name": "Bandung Air Quality",
        "endpoint_name": "Bandung Air Quality Index",
        "policies": [
            _prepaid_policy(
                "IDR", 1500, [("Starter 30k", 30_000), ("Pro 150k", 150_000)]
            )
        ],
    },
    {
        "username": "nyc-markets",
        "full_name": "NYC Market Data",
        "endpoint_name": "NYC Market Ticks",
        "policies": [
            _prepaid_policy("USD", 0.40, [("Small $10", 10), ("Large $50", 50)])
        ],
    },
    {
        "username": "sf-weather",
        "full_name": "SF Weather Labs",
        "endpoint_name": "SF Weather Stream",
        "policies": [
            _prepaid_policy("USD", 0.25, [("Small $5", 5), ("Large $25", 25)])
        ],
    },
    {
        "username": "open-gov",
        "full_name": "Open Gov Records",
        "endpoint_name": "Public Records Search",
        "policies": [],  # free — no settlement required
    },
    {
        "username": "metered-labs",
        "full_name": "Metered Labs",
        "endpoint_name": "Sensor Grid (metered)",
        "policies": [_mpp_policy()],  # MPP / Hub wallet
    },
]

# Curated shared-endpoint subsets keyed by the publisher usernames they include.
SHARED_ENDPOINTS: list[dict] = [
    {
        "name": "Indonesia Sources",
        "slug": "indonesia",
        "description": "Indonesian open-data feeds (IDR-priced).",
        "members": ["jakarta-data", "bandung-air"],
    },
    {
        "name": "Markets",
        "slug": "markets",
        "description": "USD-priced market & weather streams.",
        "members": ["nyc-markets", "sf-weather"],
    },
]

ALL_USERNAMES = [BUYER_USERNAME, *(p["username"] for p in PUBLISHERS)]


def _slugify(name: str) -> str:
    """Lowercase, hyphenated slug for an endpoint name."""
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug[:63] or "endpoint"


def _wipe(session: Session) -> None:
    """Remove previously-seeded demo entities so reseeding is clean.

    Deletes via the ORM so cascades fire: a collective drops its members and
    shared endpoints, an endpoint drops its membership rows.
    """
    users = (
        session.execute(select(UserModel).where(UserModel.username.in_(ALL_USERNAMES)))
        .scalars()
        .all()
    )
    user_ids = [u.id for u in users]

    collective = session.execute(
        select(CollectiveModel).where(CollectiveModel.slug == COLLECTIVE_SLUG)
    ).scalar_one_or_none()
    if collective is not None:
        session.delete(collective)
        session.flush()

    if user_ids:
        endpoints = (
            session.execute(
                select(EndpointModel).where(EndpointModel.user_id.in_(user_ids))
            )
            .scalars()
            .all()
        )
        for endpoint in endpoints:
            session.delete(endpoint)
        session.flush()
        for user in users:
            session.delete(user)
        session.flush()


def _make_user(session: Session, username: str, full_name: str) -> UserModel:
    """Create an active, email-verified local user."""
    user = UserModel(
        username=username,
        email=f"{username}@example.com",
        full_name=full_name,
        role="user",
        password_hash=hash_password(DEMO_PASSWORD),
        is_active=True,
        is_email_verified=True,
        auth_provider="local",
    )
    session.add(user)
    session.flush()
    return user


def seed(reset: bool) -> None:
    """Create the demo users, endpoints, collective and shared endpoints.

    Schema management is intentionally NOT done here — the backend owns its
    migrations (it runs them on startup). This script only inserts rows, so it
    must run against an already-migrated database (the Docker dev Postgres or a
    backend that has booted at least once).
    """
    table_names = set(inspect(engine).get_table_names())
    missing = {"users", "endpoints", "collectives"} - table_names
    if missing:
        print(
            "Database schema is not ready (missing tables: "
            f"{', '.join(sorted(missing))}).\n"
            "Start the backend once so it runs migrations, then re-run this "
            "script. With Docker:\n"
            "  docker compose -f deploy/docker-compose.dev.yml up -d backend"
        )
        sys.exit(1)
    with Session(engine) as session:
        existing = session.execute(
            select(CollectiveModel).where(CollectiveModel.slug == COLLECTIVE_SLUG)
        ).scalar_one_or_none()
        if existing is not None and not reset:
            print(
                f"Collective '{COLLECTIVE_SLUG}' already exists. "
                "Re-run with --reset to wipe and reseed."
            )
            return

        if reset:
            _wipe(session)

        # Buyer / collective owner.
        buyer = _make_user(session, BUYER_USERNAME, "Demo Buyer")

        # Publishers + their endpoints.
        endpoint_by_username: dict[str, EndpointModel] = {}
        for spec in PUBLISHERS:
            publisher = _make_user(session, spec["username"], spec["full_name"])
            endpoint = EndpointModel(
                user_id=publisher.id,
                name=spec["endpoint_name"],
                slug=_slugify(spec["endpoint_name"]),
                description=f"{spec['endpoint_name']} — demo data source.",
                type="data_source",
                visibility="public",
                is_active=True,
                archived=False,
                version="1.0.0",
                tags=["demo", "apac"],
                policies=spec["policies"],
            )
            session.add(endpoint)
            session.flush()
            endpoint_by_username[spec["username"]] = endpoint

        # Collective owned by the buyer; every endpoint is an approved member.
        collective = CollectiveModel(
            owner_id=buyer.id,
            name=COLLECTIVE_NAME,
            slug=COLLECTIVE_SLUG,
            description="Mixed-currency open-data collective for demoing pricing & settlement.",
            about=(
                "# APAC Open Data\n\n"
                "A demo collective mixing IDR- and USD-priced prepaid endpoints, "
                "a free endpoint, and a metered (MPP) endpoint."
            ),
            auto_approve=True,
            tags=["demo", "open-data"],
            verified=True,
        )
        session.add(collective)
        session.flush()

        for endpoint in endpoint_by_username.values():
            session.add(
                CollectiveMemberModel(
                    collective_id=collective.id,
                    endpoint_id=endpoint.id,
                    status="approved",
                    reviewed_by_user_id=buyer.id,
                )
            )
        session.flush()

        # Curated shared-endpoint subsets.
        for spec in SHARED_ENDPOINTS:
            shared = CollectiveSharedEndpointModel(
                collective_id=collective.id,
                name=spec["name"],
                slug=spec["slug"],
                description=spec["description"],
            )
            session.add(shared)
            session.flush()
            for username in spec["members"]:
                endpoint = endpoint_by_username[username]
                session.add(
                    CollectiveSharedEndpointMemberModel(
                        shared_endpoint_id=shared.id,
                        endpoint_id=endpoint.id,
                    )
                )
        session.commit()

    _print_summary()


def _print_summary() -> None:
    """Print what was seeded and how to exercise it."""
    print("\n" + "=" * 64)
    print("Seeded demo collective for pricing + settlement flows")
    print("=" * 64)
    print(f"Buyer login : {BUYER_USERNAME} / {DEMO_PASSWORD}")
    print(f"Collective  : /c/{COLLECTIVE_SLUG}   (collective/{COLLECTIVE_SLUG})")
    print("\nMembers:")
    print("  jakarta-data   IDR 2,500 / request   (prepaid)")
    print("  bandung-air    IDR 1,500 / request   (prepaid)")
    print("  nyc-markets    USD 0.40  / request   (prepaid)")
    print("  sf-weather     USD 0.25  / request   (prepaid)")
    print("  open-gov       free                  (no settlement)")
    print("  metered-labs   USD 0.30 / request    (MPP / Hub wallet)")
    print("\nExpected estimated prices:")
    print(f"  collective/{COLLECTIVE_SLUG}            ~4,000 IDR + 0.95 USD  (+1 free)")
    print(f"  collective/{COLLECTIVE_SLUG}/indonesia  ~4,000 IDR")
    print(f"  collective/{COLLECTIVE_SLUG}/markets    ~0.65 USD")
    print("=" * 64)


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Wipe previously-seeded demo entities before reseeding.",
    )
    args = parser.parse_args()
    print(f"Database URL: {settings.database_url}")
    seed(reset=args.reset)


if __name__ == "__main__":
    main()
