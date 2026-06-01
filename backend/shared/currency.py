"""Devises ISO 4217 du modèle monétaire (ADR 0008).

Le modèle reste multi-devise ; l'usage fonctionnel V1 est verrouillé à EUR au
boundary métier (`household.base_currency`, ADR 0008), PAS dans ce type qui est
agnostique. Le passage V1->V2 est alors un changement de code (ajout d'un code
au `Literal`), pas une migration de données.

Couche `shared/` : n'importe RIEN de `backend.modules.*` (import-linter #3).
"""

from __future__ import annotations

from typing import Final, Literal, get_args

from pydantic import TypeAdapter

Currency = Literal["EUR", "USD", "GBP", "CHF"]
"""Codes ISO 4217 supportés. Extensible — V1 reste EUR-only au boundary métier."""

CURRENCIES: Final[frozenset[str]] = frozenset(get_args(Currency))
"""Ensemble runtime des codes, dérivé de `Currency` (source unique de vérité)."""

# Symbole d'affichage par devise. `$`/`£`/`€` sont uniques dans notre set ;
# `CHF` n'a pas de glyphe mono-caractère stable -> on garde le code comme symbole
# (sans ambiguïté dans les 4 codes). Réversible 1-1 pour le round-trip (P07.1.3) :
# l'invariant « aucun symbole n'est suffixe d'un autre » est GARDÉ par un test
# (sans lui, `parse_french`/`endswith` deviendrait ambigu à une extension V2).
CURRENCY_SYMBOLS: Final[dict[Currency, str]] = {
    "EUR": "€",
    "USD": "$",
    "GBP": "£",
    "CHF": "CHF",
}

_CURRENCY_ADAPTER: Final[TypeAdapter[Currency]] = TypeAdapter(Currency)


def validate_currency(value: str) -> Currency:
    """Valide un code brut en `Currency` (boundary NON-Pydantic, ex. services S07.4+).

    Lève `pydantic.ValidationError` sur un code inconnu — même logique que la
    validation implicite du `Literal` au boundary Pydantic de `Money`.
    """
    return _CURRENCY_ADAPTER.validate_python(value)
