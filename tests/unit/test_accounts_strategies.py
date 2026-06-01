"""Propriétés pures sur la strategy partagée `account_with_members_strategy` (S05.5, P05.5.1).

Verrouille par property-based testing les invariants de la strategy et leur
acceptation par le domaine pur (`AccountValidator`) — aucun accès DB, périmètre
`Stratégie de tests §4.2` (Hypothesis sur le domaine pur uniquement).

⚠️ `test_property_generated_account_is_accepted` est un **test de cohérence
strategy↔validator** : `share_ratios` encode par construction les mêmes règles
que `validate` vérifie (Σ=1, ≥2, >0, sans doublon, EUR), donc il garantit surtout
qu'ils restent synchronisés. La garantie *indépendante* (un roster invalide est
rejeté) vit dans les propriétés de rejet de `test_accounts_validator.py`.
"""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

from hypothesis import given

from backend.modules.accounts.domain import AccountType, AccountValidator
from tests import strategies
from tests.strategies import (
    GeneratedAccount,
    account_with_members_strategy,
)

_BASE = "EUR"


def _validate(account: GeneratedAccount) -> None:
    AccountValidator.validate(
        currency=account.currency,
        household_base_currency=_BASE,
        owner_id=account.owner_id,
        members=account.members,
    )


@given(account=account_with_members_strategy())
def test_property_generated_account_is_accepted(account: GeneratedAccount) -> None:
    # ∀ compte issu de la strategy → AccountValidator l'accepte (aucun contre-exemple).
    # Test de cohérence strategy↔validator (cf. docstring du module).
    _validate(account)


@given(
    account=account_with_members_strategy(
        shape="shared",
        account_type=AccountType.LIVRET,
        user_ids=[uuid4(), uuid4()],
    )
)
def test_property_generated_shared_with_fixed_axes_is_accepted(account: GeneratedAccount) -> None:
    # Forcer la catégorie (décorative) ET ancrer les membres ne casse pas la
    # validité : type imposé != forme, owner_id reste None, 2 membres Σ=1.
    assert account.type is AccountType.LIVRET
    assert account.owner_id is None
    assert len(account.members) == 2
    _validate(account)


@given(account=account_with_members_strategy(shape="personal"))
def test_property_personal_has_no_members(account: GeneratedAccount) -> None:
    # Un compte généré `personal` a un owner et 0 membre.
    assert account.owner_id is not None
    assert account.members == []
    _validate(account)


@given(account=account_with_members_strategy(shape="shared"))
def test_property_shared_has_at_least_two_members(account: GeneratedAccount) -> None:
    # Un compte généré `shared` a owner_id=None et ≥ 2 membres.
    assert account.owner_id is None
    assert len(account.members) >= 2
    _validate(account)


@given(account=account_with_members_strategy(shape="shared"))
def test_property_shared_ratios_sum_to_one_exact(account: GeneratedAccount) -> None:
    # Σ des quote-parts == Decimal("1.0000") exact (pas de tolérance float).
    total = sum((m.ratio for m in account.members), start=Decimal("0"))
    assert total == Decimal("1.0000")


@given(account=account_with_members_strategy(shape="shared"))
def test_generated_ratios_are_decimal_never_float(account: GeneratedAccount) -> None:
    # Critère d'acceptation : pas de `float` dans la génération des ratios.
    for member in account.members:
        assert isinstance(member.ratio, Decimal)


@given(account=account_with_members_strategy(shape="shared", n_members=4))
def test_property_n_members_is_honoured(account: GeneratedAccount) -> None:
    # `n_members` fixe exactement la cardinalité d'un commun.
    assert len(account.members) == 4
    assert len({m.user_id for m in account.members}) == 4
    _validate(account)


def test_strategy_importable_without_side_effect() -> None:
    # Contrat du `tests/strategies.py` : importable sans effet de bord (le module
    # est déjà importé au chargement de ce fichier ; on vérifie juste le contrat
    # d'API public, sans instancier ni toucher de ressource externe).
    assert callable(strategies.account_with_members_strategy)
    assert callable(strategies.share_ratios)
    assert issubclass(strategies.GeneratedAccount, object)
