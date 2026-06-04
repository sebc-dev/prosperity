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

from decimal import ROUND_HALF_UP, Decimal
from functools import total_ordering
from typing import Final

from pydantic import ConfigDict
from pydantic.dataclasses import dataclass

from backend.shared.currency import CURRENCY_SYMBOLS, Currency

# ---------------------------------------------------------------------------
# Constantes de formatage / parsing FR (lues par `Money.format_french` et
# `parse_french` ci-dessous ; définies en tête pour l'ordre de lecture).
# ---------------------------------------------------------------------------

_CENTS_PER_UNIT: Final[int] = 100
_THOUSANDS_SEP: Final[str] = " "  # U+202F espace fine insécable (milliers)
_CURRENCY_GAP: Final[str] = " "  # U+00A0 espace insécable (avant le symbole)
_DECIMAL_SEP: Final[str] = ","
# Normalisation parse : toute variante d'espace est supprimée -> round-trip robuste.
_SPACE_TRANSLATION: Final = {0x202F: None, 0x00A0: None, 0x20: None}
_DECIMAL_DIGITS: Final[int] = 2
_ASCII_DIGITS: Final = frozenset("0123456789")  # rejette les chiffres Unicode


def _is_ascii_digits(s: str) -> bool:
    """`True` ssi `s` est non vide et composé UNIQUEMENT de chiffres ASCII 0-9.

    `str.isdigit()` accepte les chiffres Unicode (fullwidth, arabe-indic, exposants)
    -> on s'en prémunit pour ne pas accepter silencieusement `"１２,３４ €"`.
    """
    return bool(s) and set(s) <= _ASCII_DIGITS


def _group_thousands(units: int) -> str:
    """`1234` -> `"1 234"` (groupes de 3, séparés par `U+202F`). `units >= 0`."""
    s = str(units)
    parts: list[str] = []
    while len(s) > 3:  # noqa: PLR2004 — groupes de 3 chiffres (notation des milliers)
        parts.insert(0, s[-3:])
        s = s[:-3]
    parts.insert(0, s)
    return _THOUSANDS_SEP.join(parts)


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

    def apply_ratio(self, ratio: Decimal) -> Money:
        """Applique une quote-part `Decimal` au montant et arrondit aux cents.

        Primitif arithmétique PUR : multiplie puis arrondit, SANS borne sur
        `ratio` (`ratio > 1` est légitime ici → agrandit ; la borne métier
        `0 < r ≤ 1` vit dans `DebtCalculator`, PAS dans le value object —
        séparation primitif/règle, S09.2 D6).

        `ROUND_HALF_UP` (arrondi commercial, prévisible pour des montants) :
        `Money(5, "EUR").apply_ratio(Decimal("0.5")) == Money(3, "EUR")` (2,5¢ →
        3¢, et non 2¢ comme HALF_EVEN). Politique cents centralisée ici (jamais
        de `float` ; les `Decimal` du projet servent aux quote-parts, pas aux
        montants — ADR 0008). `ratio: float` lève `TypeError` (`Decimal * float`
        interdit) — garde-fou de facto de « jamais de float ». Devise préservée.
        """
        rounded = int(
            (Decimal(self.amount_cents) * ratio).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        )
        return Money(rounded, self.currency)

    def format_french(self) -> str:
        """`Money(123456, "EUR")` -> `"1 234,56 €"` (typographie FR).

        Milliers = espace fine insécable `U+202F` ; séparateur décimal = virgule ;
        espace insécable `U+00A0` avant le symbole de devise.
        """
        sign = "-" if self.amount_cents < 0 else ""
        units, cents = divmod(abs(self.amount_cents), _CENTS_PER_UNIT)
        symbol = CURRENCY_SYMBOLS[self.currency]
        return f"{sign}{_group_thousands(units)}{_DECIMAL_SEP}{cents:02d}{_CURRENCY_GAP}{symbol}"


def parse_french(text: str) -> Money:
    """Inverse de `format_french` : `"1 234,56 €"` -> `Money(123456, "EUR")`.

    Politique de parsing (tranchée explicitement) :

    - **Symbole de devise OBLIGATOIRE** en suffixe (sinon `ValueError`).
    - **Partie décimale OBLIGATOIRE** : exactement le séparateur `,` + 2 chiffres
      ASCII (sinon `ValueError` — pas de virgule, mauvais nb de décimales, chiffres
      non-ASCII rejetés).
    - **Groupage des milliers LAXISTE** : tout espace (`U+202F`/`U+00A0`/`U+0020`)
      est normalisé/supprimé avant lecture ; le placement des séparateurs n'est PAS
      vérifié (`"1234,56 €"` comme `"1 234,56 €"` sont acceptés). Le signe `-` n'est
      lu qu'après cette normalisation, donc un signe détaché (`"- 1 234,56 €"`) est
      lui aussi toléré. Choix assumé : l'invariant contractuel est
      `parse_french(m.format_french()) == m`, pas l'inverse ; un groupage
      utilisateur libre est toléré.

    Garantit le round-trip : ∀ `m`, `parse_french(m.format_french()) == m`.
    """
    raw = text.strip()
    for code, symbol in CURRENCY_SYMBOLS.items():
        if raw.endswith(symbol):
            body = raw[: -len(symbol)]
            currency = code
            break
    else:
        raise ValueError(f"Symbole de devise inconnu dans : {text!r}")
    body = body.translate(_SPACE_TRANSLATION)
    negative = body.startswith("-")
    body = body.removeprefix("-")
    units_str, sep, cents_str = body.partition(_DECIMAL_SEP)
    if (
        not sep
        or len(cents_str) != _DECIMAL_DIGITS
        or not _is_ascii_digits(units_str)
        or not _is_ascii_digits(cents_str)
    ):
        raise ValueError(f"Montant FR invalide : {text!r}")
    amount = int(units_str) * _CENTS_PER_UNIT + int(cents_str)
    # `currency` est une clé de CURRENCY_SYMBOLS => déjà un `Currency` valide
    # (pas de `validate_currency` redondant ici).
    return Money(-amount if negative else amount, currency)
