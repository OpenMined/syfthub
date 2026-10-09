"""``Money`` and ``Bundle``. Amounts are Decimals; currencies are never converted."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from ..errors import ValidationError
from .base import Frozen


class Money(Frozen):
    amount: Decimal = Decimal(0)
    currency: str = "USD"

    @classmethod
    def of(cls, amount: Decimal | float | str | int, currency: str = "USD") -> Money:
        try:
            dec = amount if isinstance(amount, Decimal) else Decimal(str(amount))
        except InvalidOperation as e:
            raise ValidationError(f"not an amount: {amount!r}") from e
        return cls(amount=dec, currency=currency.upper())

    @classmethod
    def zero(cls, currency: str = "USD") -> Money:
        return cls(amount=Decimal(0), currency=currency)

    def _check(self, other: Any) -> Money:
        if not isinstance(other, Money):
            raise TypeError(f"expected Money, got {type(other).__name__}")
        if other.currency != self.currency:
            raise ValidationError(f"currency mismatch: {self.currency} vs {other.currency}")
        return other

    def __add__(self, other: Money) -> Money:
        o = self._check(other)
        return Money(amount=self.amount + o.amount, currency=self.currency)

    def __sub__(self, other: Money) -> Money:
        o = self._check(other)
        return Money(amount=self.amount - o.amount, currency=self.currency)

    def __mul__(self, n: int) -> Money:
        return Money(amount=self.amount * n, currency=self.currency)

    def __lt__(self, other: Money) -> bool:
        return self.amount < self._check(other).amount

    def __le__(self, other: Money) -> bool:
        return self.amount <= self._check(other).amount

    def __gt__(self, other: Money) -> bool:
        return self.amount > self._check(other).amount

    def __ge__(self, other: Money) -> bool:
        return self.amount >= self._check(other).amount

    @property
    def positive(self) -> bool:
        return self.amount > 0

    def __str__(self) -> str:
        return f"{self.amount.normalize():f} {self.currency}"


class Bundle(Frozen):
    """One purchasable top-up, from the payment policy's ``bundles[]``."""

    id: str
    amount: Money
    credits: Money | None = None

    @property
    def granted(self) -> Money:
        """What lands in the wallet: ``credits`` when the policy says, else ``amount``."""
        return self.credits if self.credits is not None else self.amount
