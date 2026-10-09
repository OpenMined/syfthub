"""Shared fixtures: Hub-shaped source bodies and a wallet."""

from __future__ import annotations

from typing import Any

import pytest

from syfthub import Rail, Source, Wallet


def hub_body(
    owner: str,
    slug: str,
    *,
    type: str = "data_source",
    policies: list[dict[str, Any]] | None = None,
    health: str | None = "healthy",
    tags: list[str] | None = None,
    description: str = "",
) -> dict[str, Any]:
    return {
        "name": slug.replace("-", " ").title(),
        "slug": slug,
        "description": description,
        "type": type,
        "owner_username": owner,
        "contributors_count": 1,
        "version": "1.0.0",
        "readme": "# readme",
        "tags": tags or [],
        "stars_count": 3,
        "policies": policies or [],
        "connect": [
            {"type": "http", "enabled": True, "config": {"url": f"https://{owner}.space.test"}}
        ],
        "created_at": "2026-10-01T00:00:00Z",
        "updated_at": "2026-10-02T00:00:00Z",
        "health_status": health,
        "health_checked_at": "2026-10-02T00:00:00Z",
        "archived": False,
        "some_future_field": {"kept": "in raw"},
    }


def xendit_policy(**overrides: Any) -> dict[str, Any]:
    config: dict[str, Any] = {
        "payment_url": "https://erin.space.test/api/payments",
        "credits_url": "https://erin.space.test/api/credits",
        "invoices_url": "https://erin.space.test/api/invoices",
        "currency": "USD",
        "price": 0.05,
        "unit_type": "request",
        "bundles": [{"name": "starter", "amount": 1}, {"name": "pro", "amount": 10}],
        "wallet_id": "w-erin",
    }
    config.update(overrides)
    return {"type": "xendit", "enabled": True, "config": config}


@pytest.fixture
def free_source() -> Source:
    return Source.from_hub(
        hub_body("alice", "free-docs", tags=["clinical"], description="trial notes")
    )


@pytest.fixture
def paid_source() -> Source:
    return Source.from_hub(
        hub_body("erin", "trials", policies=[xendit_policy()], tags=["clinical", "phase3"])
    )


@pytest.fixture
def model_source() -> Source:
    return Source.from_hub(hub_body("kim", "assistant", type="model", health=None))


@pytest.fixture
def wallet(paid_source: Source) -> Wallet:
    pricing = paid_source.pricing
    assert pricing is not None
    return Wallet(
        id="w-erin",
        key="erin/xendit/USD",
        owner="erin",
        rail=Rail.XENDIT,
        currency="USD",
        sources=(paid_source.path,),
        bundles=pricing.bundles,
        payment_url=pricing.payment_url,
        credits_url=pricing.credits_url,
        invoices_url=pricing.invoices_url,
    )
