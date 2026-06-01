"""Value object monétaire immutable `(amount_cents, currency)` (glossaire §Money).

`amount_cents: int` — centimes entiers, JAMAIS de `float` ni `Decimal` (ADR 0008 ;
les `Decimal` du projet servent aux quote-parts, pas aux montants). Arithmétique
cross-devise INTERDITE au niveau du type : `+`, `-` et l'ordre lèvent
`IncompatibleCurrencyError`. `==` cross-devise renvoie simplement `False`
(inégalité, pas erreur).

PAS un modèle ORM : `Split` (S07.2) stocke `amount_cents` + `currency` en colonnes
séparées ; le service mappe `(amount_cents, currency) <-> Money`. Couche `shared/` :
n'importe RIEN de `backend.modules.*` (import-linter #3).
"""

from __future__ import annotations

from functools import total_ordering

from pydantic import ConfigDict
from pydantic.dataclasses import dataclass

from backend.shared.currency import Currency


class IncompatibleCurrencyError(Exception):
    """Opération arithmétique ou comparaison d'ordre entre devises distinctes.

    Hérite directement d'`Exception` : `shared/` n'a pas de taxonomie d'erreurs
    (une seule exception métier ici — pas de base commune à introduire, D8).
    """

    def __init__(self, left: Currency, right: Currency) -> None:
        super().__init__(f"Opération cross-devise interdite : {left} vs {right}")
        self.left = left
        self.right = right


@total_ordering
@dataclass(frozen=True, config=ConfigDict(strict=True))
class Money:
    """Montant monétaire immutable. Construction positionnelle : `Money(100, "EUR")`.

    `==` est structurel : deux devises différentes sont *inégales* (`False`), pas
    une erreur. Seuls `+`, `-` et l'ordre (`<`, `<=`, ...) lèvent
    `IncompatibleCurrencyError` cross-devise. `__hash__`/`__eq__` fournis par la
    dataclass frozen (par `(amount_cents, currency)`) ; `@total_ordering` dérive
    `__le__`/`__gt__`/`__ge__` depuis `__lt__` + `__eq__`.
    """

    amount_cents: int
    currency: Currency

    def _same_currency(self, other: Money) -> None:
        if self.currency != other.currency:
            raise IncompatibleCurrencyError(self.currency, other.currency)

    def __add__(self, other: object) -> Money:
        if not isinstance(other, Money):
            return NotImplemented
        self._same_currency(other)
        return Money(self.amount_cents + other.amount_cents, self.currency)

    def __sub__(self, other: object) -> Money:
        if not isinstance(other, Money):
            return NotImplemented
        self._same_currency(other)
        return Money(self.amount_cents - other.amount_cents, self.currency)

    def __mul__(self, factor: object) -> Money:
        # `bool` est sous-classe d'`int` mais `money * True` n'a pas de sens ;
        # tout non-`int` (`float`, ...) -> NotImplemented -> `TypeError` Python.
        if not isinstance(factor, int) or isinstance(factor, bool):
            return NotImplemented
        return Money(self.amount_cents * factor, self.currency)

    __rmul__ = __mul__

    def __neg__(self) -> Money:
        return Money(-self.amount_cents, self.currency)

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, Money):
            return NotImplemented
        self._same_currency(other)
        return self.amount_cents < other.amount_cents
