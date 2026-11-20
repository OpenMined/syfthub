"""``Money`` and ``Bundle``. Amounts are Decimals; currencies are never converted."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from ..errors import ValidationError
from .base import Frozen


class Money(Frozen):
    """An exact amount in one currency."""

    amount: Decimal = Decimal(0)
    currency: str = "USD"

    @classmethod
    def of(cls, amount: Decimal | float | str | int, currency: str = "USD") -> Money:
        """``Money`` from a number or a string.

        ``Money.of(1.5)`` and ``Money.of("1.5")`` agree: the float goes through ``str`` first.

        Args:
            amount: a ``Decimal``, number or numeric string.
            currency: an ISO code.

        Returns:
            The amount.
        """
        try:
            dec = amount if isinstance(amount, Decimal) else Decimal(str(amount))
        except InvalidOperation as e:
            raise ValidationError(f"not an amount: {amount!r}") from e
        return cls(amount=dec, currency=currency.upper())

    @classmethod
    def zero(cls, currency: str = "USD") -> Money:
        """Nothing, in ``currency``.

        Args:
            currency: an ISO code.

        Returns:
            Zero in that currency.
        """
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
        """True above zero."""
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
