from decimal import Decimal

import pytest

from syfthub import Bundle, Money, ValidationError


def test_of_normalises_and_uppercases() -> None:
    m = Money.of(0.1, "usd")
    assert m.amount == Decimal("0.1") and m.currency == "USD"
    assert str(Money.of("1.250")) == "1.25 USD"


def test_arithmetic_and_comparison() -> None:
    a, b = Money.of(1), Money.of("0.25")
    assert (a + b).amount == Decimal("1.25")
    assert (a - b).amount == Decimal("0.75")
    assert (b * 3).amount == Decimal("0.75")
    assert b < a and a >= b and not a < b
    assert Money.zero().positive is False and a.positive


def test_currency_mismatch_raises_sdk_validation_error() -> None:
    with pytest.raises(ValidationError):
        Money.of(1, "USD") + Money.of(1, "IDR")


def test_to_dict_is_plain_json() -> None:
    assert Money.of("1.25").to_dict() == {"amount": "1.25", "currency": "USD"}
    assert Money.from_dict({"amount": "1.25", "currency": "USD"}) == Money.of("1.25")


def test_bundle_granted_falls_back_to_amount() -> None:
    b = Bundle(id="starter", amount=Money.of(5))
    assert b.granted == Money.of(5)
    assert Bundle(id="x", amount=Money.of(5), credits=Money.of(6)).granted == Money.of(6)
