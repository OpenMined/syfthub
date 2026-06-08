"""Unit tests for the collective billing-summary classification helpers.

These exercise the pure ``collective_service`` functions that reduce an
endpoint's policies to a normalized :class:`MemberBillingDetail` — the logic
behind the estimated-price badge and the settlement modal — without touching
the database.
"""

from types import SimpleNamespace
from typing import Any

from syfthub.services.collective_service import (
    _classify_billing,
    _parse_per_request_price,
    _parse_prepaid_config,
    _parse_unit,
)


def _policy(ptype: str, config: dict[str, Any], *, enabled: bool = True) -> Any:
    """A minimal stand-in for an endpoint Policy."""
    return SimpleNamespace(type=ptype, config=config, enabled=enabled)


def _endpoint(*policies: Any) -> Any:
    """A minimal stand-in for an Endpoint with the given policies."""
    return SimpleNamespace(policies=list(policies))


_PREPAID_CONFIG = {
    "payment_url": "https://pay.example.com/invoice",
    "credits_url": "https://pay.example.com/balance",
    "currency": "IDR",
    "price": 2500,
    "unit_type": "request",
    "bundles": [{"name": "Starter", "amount": 50000}],
}


# ----------------------------------------------------------------------
# _parse_unit
# ----------------------------------------------------------------------


def test_parse_unit_request_and_document() -> None:
    assert _parse_unit({"unit_type": "request"}) == "request"
    assert _parse_unit({"unit_type": "document"}) == "document"
    # camelCase is accepted too.
    assert _parse_unit({"unitType": "document"}) == "document"


def test_parse_unit_defaults_to_request() -> None:
    assert _parse_unit({}) == "request"
    assert _parse_unit({"unit_type": "nonsense"}) == "request"


# ----------------------------------------------------------------------
# _parse_prepaid_config
# ----------------------------------------------------------------------


def test_parse_prepaid_config_valid() -> None:
    parsed = _parse_prepaid_config(_PREPAID_CONFIG)
    assert parsed is not None
    assert parsed["currency"] == "IDR"
    assert parsed["price_per_unit"] == 2500
    assert parsed["unit"] == "request"
    assert parsed["payment_url"] == "https://pay.example.com/invoice"
    assert parsed["credits_url"] == "https://pay.example.com/balance"
    assert len(parsed["bundles"]) == 1
    assert parsed["bundles"][0].name == "Starter"
    assert parsed["bundles"][0].amount == 50000


def test_parse_prepaid_config_accepts_camel_case() -> None:
    parsed = _parse_prepaid_config(
        {
            "paymentUrl": "https://pay.example.com/invoice",
            "creditsUrl": "https://pay.example.com/balance",
        }
    )
    assert parsed is not None
    assert parsed["payment_url"] == "https://pay.example.com/invoice"
    # Currency falls back to IDR (mirrors the frontend parseXenditConfig).
    assert parsed["currency"] == "IDR"


def test_parse_prepaid_config_legacy_price_key() -> None:
    config = {**_PREPAID_CONFIG}
    del config["price"]
    config["price_per_request"] = 999
    parsed = _parse_prepaid_config(config)
    assert parsed is not None
    assert parsed["price_per_unit"] == 999


def test_parse_prepaid_config_requires_both_urls() -> None:
    # Missing credits_url → not settlable → None.
    assert _parse_prepaid_config({"payment_url": "https://pay.example.com"}) is None
    # Missing payment_url → None.
    assert _parse_prepaid_config({"credits_url": "https://pay.example.com"}) is None
    # Non-http values are rejected.
    assert (
        _parse_prepaid_config({"payment_url": "ftp://x", "credits_url": "ftp://y"})
        is None
    )


def test_parse_prepaid_config_invoices_url_optional() -> None:
    parsed = _parse_prepaid_config(_PREPAID_CONFIG)
    assert parsed is not None
    assert parsed["invoices_url"] is None
    parsed2 = _parse_prepaid_config(
        {**_PREPAID_CONFIG, "invoices_url": "https://pay.example.com/invoices"}
    )
    assert parsed2 is not None
    assert parsed2["invoices_url"] == "https://pay.example.com/invoices"


# ----------------------------------------------------------------------
# _parse_per_request_price (MPP)
# ----------------------------------------------------------------------


def test_parse_per_request_price_variants() -> None:
    assert _parse_per_request_price({"currency": "USD", "price": 0.5}) == (
        "USD",
        0.5,
        "request",
    )
    assert _parse_per_request_price({"price_per_request": 1.5}) == (
        "USD",
        1.5,
        "request",
    )
    assert _parse_per_request_price({"price_per_call": 2.0}) == ("USD", 2.0, "request")


def test_parse_per_request_price_missing_price() -> None:
    currency, price, unit = _parse_per_request_price({})
    assert currency == "USD"
    assert price is None
    assert unit == "request"


# ----------------------------------------------------------------------
# _classify_billing — precedence + bucketing
# ----------------------------------------------------------------------


def test_classify_prepaid_wins_over_mpp() -> None:
    detail = _classify_billing(
        _endpoint(
            _policy("mpp_accounting", {"price": 1.0, "currency": "USD"}),
            _policy("xendit", _PREPAID_CONFIG),
        )
    )
    assert detail.kind == "prepaid"
    assert detail.provider == "xendit"
    assert detail.currency == "IDR"


def test_classify_mpp_when_only_metered_policy() -> None:
    detail = _classify_billing(
        _endpoint(_policy("mpp_accounting", {"price": 3.0, "currency": "USD"}))
    )
    assert detail.kind == "mpp"
    assert detail.price_per_unit == 3.0
    assert detail.currency == "USD"


def test_classify_free_when_no_billing_policy() -> None:
    detail = _classify_billing(_endpoint())
    assert detail.kind == "free"
    assert detail.price_per_unit is None


def test_classify_disabled_policies_ignored() -> None:
    detail = _classify_billing(
        _endpoint(_policy("xendit", _PREPAID_CONFIG, enabled=False))
    )
    assert detail.kind == "free"


def test_classify_prepaid_missing_urls_falls_through_to_mpp() -> None:
    # A prepaid policy that can't drive settlement is ignored, and the metered
    # policy is used instead.
    detail = _classify_billing(
        _endpoint(
            _policy("stripe", {"price": 5}),  # no usable URLs
            _policy("accounting", {"price": 1.25, "currency": "USD"}),
        )
    )
    assert detail.kind == "mpp"
    assert detail.price_per_unit == 1.25


def test_classify_stripe_provider_recorded() -> None:
    detail = _classify_billing(_endpoint(_policy("stripe", _PREPAID_CONFIG)))
    assert detail.kind == "prepaid"
    assert detail.provider == "stripe"
