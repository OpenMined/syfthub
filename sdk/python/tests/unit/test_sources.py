from __future__ import annotations

import pytest

from syfthub import Health, Policy, PriceUnit, Rail, Source, SourceList, SourceType
from syfthub.models import pricing_from_policies

from .conftest import hub_body, xendit_policy


def test_from_hub_keeps_raw_and_maps_health(free_source: Source) -> None:
    assert free_source.path == "alice/free-docs"
    assert free_source.health is Health.HEALTHY
    assert free_source.raw["some_future_field"] == {"kept": "in raw"}
    assert free_source.space_url == "https://alice.space.test"
    assert free_source.free and free_source.pricing is None
    assert free_source.type.returns_documents


def test_unknown_health_and_model_type(model_source: Source) -> None:
    assert model_source.health is Health.UNKNOWN
    assert model_source.type is SourceType.MODEL and model_source.type.returns_summary


def test_unknown_policy_type_still_parses() -> None:
    src = Source.from_hub(
        hub_body("bob", "x", policies=[{"type": "brand_new", "config": {"a": 1}}])
    )
    assert src.policies[0].known is None and not src.policies[0].is_payment
    assert src.pricing is None


def test_prepaid_pricing_from_xendit_policy(paid_source: Source) -> None:
    p = paid_source.pricing
    assert p is not None
    assert p.rail is Rail.XENDIT and p.rail.prepaid
    assert str(p.price) == "0.05 USD" and p.unit is PriceUnit.REQUEST
    assert p.wallet_id == "w-erin"
    assert [b.id for b in p.bundles] == ["starter", "pro"]
    assert p.bundles[1].amount.amount == 10
    assert p.payment_url and p.credits_url and p.invoices_url
    assert p.estimate(limit=5) == p.price
    assert not paid_source.free


def test_per_document_pricing_and_legacy_price_key() -> None:
    policy = Policy(type="stripe", config={"price_per_request": 0.02, "unit_type": "document"})
    p = pricing_from_policies((policy,))
    assert p is not None and p.rail is Rail.STRIPE
    assert p.unit is PriceUnit.DOCUMENT and str(p.estimate(limit=5)) == "0.1 USD"


def test_xendit_defaults_to_idr_and_disabled_policies_are_skipped() -> None:
    disabled = Policy(type="stripe", enabled=False, config={"price": 1})
    xendit = Policy(type="xendit", config={"price": 1000})
    p = pricing_from_policies((disabled, xendit))
    assert p is not None and p.rail is Rail.XENDIT and p.price.currency == "IDR"


def test_mpp_pricing_has_no_wallet_urls() -> None:
    p = pricing_from_policies((Policy(type="mpp", config={"price": 0.01, "currency": "usd"}),))
    assert p is not None and p.rail is Rail.MPP and not p.rail.prepaid
    assert p.credits_url is None and p.bundles == ()


def test_cluster_pricing_carries_wallet_owner() -> None:
    policy = {
        "type": "cluster",
        "config": {**xendit_policy()["config"], "wallet_owner_username": "station"},
    }
    src = Source.from_hub(hub_body("erin", "shared", policies=[policy]))
    assert src.pricing is not None and src.pricing.wallet_owner == "station"
    assert src.pricing.rail is Rail.CLUSTER


@pytest.fixture
def listing(free_source: Source, paid_source: Source, model_source: Source) -> SourceList:
    return SourceList(items=(free_source, paid_source, model_source), total=42)


def test_sourcelist_lookup_and_views(listing: SourceList) -> None:
    assert len(listing) == 3 and listing.total == 42
    assert listing["erin/trials"].slug == "trials" and listing[0].owner_username == "alice"
    assert "erin/trials" in listing and "nobody/x" not in listing
    with pytest.raises(KeyError):
        listing["nobody/x"]
    assert listing.filter(owner="erin").paths == ("erin/trials",)
    assert listing.filter(free=True).paths == ("alice/free-docs", "kim/assistant")
    assert listing.filter(type="model").paths == ("kim/assistant",)
    assert listing.filter(tag="phase3").paths == ("erin/trials",)
    assert listing.pick("kim/assistant", "alice/free-docs").paths == (
        "kim/assistant",
        "alice/free-docs",
    )
    assert listing.filter(owner="erin").total == 42


def test_sourcelist_matching_is_fuzzy_and_ordered(listing: SourceList) -> None:
    assert listing.matching("trials").paths[0] == "erin/trials"
    assert "alice/free-docs" in listing.matching("clinical").paths
    assert listing.matching("zzzz-nothing").paths == ()


def test_sourcelist_add_dedupes(listing: SourceList, paid_source: Source) -> None:
    other = SourceList(items=(paid_source,), total=1)
    assert (listing + other).paths == listing.paths
    assert (other + listing).paths == ("erin/trials", "alice/free-docs", "kim/assistant")


def test_source_roundtrip(paid_source: Source) -> None:
    assert Source.from_dict(paid_source.to_dict()) == paid_source


def test_pricing_sums_per_request_and_per_document_on_one_wallet() -> None:
    per_request = xendit_policy()
    per_document = xendit_policy(price=0.02, unit_type="document")
    per_request["type"] = per_document["type"] = "stripe"
    src = Source.from_hub(hub_body("acme", "handbook-qa", policies=[per_request, per_document]))
    p = src.pricing
    assert p is not None and p.rail is Rail.STRIPE and len(p.prices) == 2
    assert str(p.estimate(limit=3)) == "0.11 USD"  # 0.05 + 3 x 0.02
    assert str(p.price) == "0.05 USD" and p.unit is PriceUnit.REQUEST


def test_space_side_type_names_also_parse() -> None:
    policy = Policy(type="stripe_per_document", config={"price": 0.02})
    p = pricing_from_policies((policy,))
    assert p is not None and p.rail is Rail.STRIPE and p.unit is PriceUnit.DOCUMENT


def test_applied_to_decides_who_pays() -> None:
    p = pricing_from_policies(
        (Policy(type="stripe", config={"price": 1, "applied_to": ["*@partner.io"]}),)
    )
    assert p is not None
    assert (
        p.applies_to("dana@partner.io")
        and not p.applies_to("eve@acme.com")
        and not p.applies_to(None)
    )
    everyone = pricing_from_policies(
        (Policy(type="stripe", config={"price": 1, "applied_to": ["*"]}),)
    )
    assert everyone is not None and everyone.applies_to(None)


def test_access_rules_mirror_the_space() -> None:
    policy = {
        "type": "access",
        "config": {
            "allowed_users": ["*@acme.com", "*@partner.io"],
            "denied_users": ["contractor-*@acme.com"],
        },
    }
    src = Source.from_hub(hub_body("acme", "handbook-qa", policies=[policy]))
    assert src.access("eve@acme.com").allowed
    assert src.access("Dana@Partner.io").allowed
    denied = src.access("contractor-1@acme.com")
    assert not denied.allowed and denied.rule == "denied_users: contractor-*@acme.com"
    outsider = src.access("bob@competitor.com")
    assert not outsider.allowed and outsider.rule is not None and "allowed_users" in outsider.rule
    assert not src.access(None).allowed
    open_src = Source.from_hub(
        hub_body("a", "b", policies=[{"type": "access", "config": {"denied_users": ["x@y"]}}])
    )
    assert open_src.access("anyone@z").allowed and not open_src.access("x@y").allowed
    assert Source.from_hub(hub_body("a", "b")).access(None).allowed


def test_query_url_and_reachability() -> None:
    src = Source.from_hub(hub_body("alice", "free-docs"))
    assert src.query_url == "https://alice.space.test/api/v1/endpoints/free-docs/query"
    body = hub_body("alice", "free-docs")
    body["connect"] = [
        {
            "type": "https",
            "enabled": True,
            "config": {"url": "https://x.test/", "path": "/api/v1/endpoints/free-docs/query"},
        }
    ]
    assert Source.from_hub(body).query_url == "https://x.test/api/v1/endpoints/free-docs/query"
    body["connect"] = [{"type": "https", "enabled": True, "config": {"url": "tunneling:alice"}}]
    tunnelled = Source.from_hub(body)
    assert not tunnelled.reachable and tunnelled.space_url == "tunneling:alice"
    body["connect"] = []
    assert Source.from_hub(body).query_url is None and not Source.from_hub(body).reachable
