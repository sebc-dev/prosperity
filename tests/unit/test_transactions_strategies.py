"""Propriétés pures sur les strategies transactions partagées (S07.6, P07.6.1).

Verrouille par property-based testing les invariants des strategies de
`tests/strategies.py` que les autres tests consomment SANS les vérifier
directement — au premier chef la cohérence *zero-sum par construction* de
`balanced_splits_strategy` (critère d'acceptation #117 : « property de cohérence
sans contre-exemple »). Aucun accès DB, périmètre `Stratégie de tests §4.2`
(Hypothesis sur le domaine pur uniquement).

⚠️ Cohérence vs indépendance : ces properties affirment que la *strategy* produit
ce qu'elle promet (somme nulle, devise unique, cardinalité, état). La garantie
*indépendante* que le domaine REJETTE un déséquilibre vit dans
`test_transactions_domain.py` (`test_property_unbalanced_splits_raise_confirmed`).
"""

from __future__ import annotations

from hypothesis import given, settings

from backend.modules.transactions.domain import (
    Split,
    Transaction,
    TransactionState,
    assert_zero_sum,
)
from backend.shared.money import Money
from tests import strategies
from tests.strategies import (
    balanced_splits_strategy,
    transaction_confirmed_strategy,
    transaction_draft_strategy,
)


@given(splits=balanced_splits_strategy())
@settings(max_examples=200)
def test_property_balanced_splits_are_zero_sum(splits: tuple[Split, ...]) -> None:
    # ∀ tirage de `balanced_splits_strategy`, sum(splits.amount) == Money(0, ccy).
    # Assertion DIRECTE sur la sortie de la strategy (et non « construit un
    # confirmed sans erreur ») — c'est la property de cohérence exigée par l'AC.
    total = sum((s.amount for s in splits[1:]), start=splits[0].amount)
    assert total == Money(0, splits[0].amount.currency)


@given(splits=balanced_splits_strategy(n_splits=4))
@settings(max_examples=100)
def test_property_balanced_splits_n_splits_honoured(splits: tuple[Split, ...]) -> None:
    # `n_splits` FIXE la cardinalité exacte (D4, signature de l'AC).
    assert len(splits) == 4  # noqa: PLR2004 — n_splits demandé explicitement


@given(splits=balanced_splits_strategy())
@settings(max_examples=100)
def test_property_balanced_splits_single_currency(splits: tuple[Split, ...]) -> None:
    # Toutes les jambes partagent une devise ⇒ pas d'IncompatibleCurrencyError
    # possible à la somme (prérequis du zero-sum via Money.__add__).
    assert len({s.amount.currency for s in splits}) == 1


@given(splits=balanced_splits_strategy(distinct_accounts=True))
@settings(max_examples=100)
def test_property_balanced_splits_distinct_accounts_true(splits: tuple[Split, ...]) -> None:
    # `distinct_accounts=True` ⇒ un account_id par jambe (forme transfert).
    assert len({s.account_id for s in splits}) == len(splits)


@given(splits=balanced_splits_strategy(distinct_accounts=False))
@settings(max_examples=100)
def test_property_balanced_splits_shared_account(splits: tuple[Split, ...]) -> None:
    # `distinct_accounts=False` ⇒ toutes les jambes sur le même compte
    # (forme dépense/revenu canonique S07.2).
    assert len({s.account_id for s in splits}) == 1


@given(tx=transaction_draft_strategy())
@settings(max_examples=100)
def test_property_draft_strategy_is_draft(tx: Transaction) -> None:
    # Le draft est construit même si sum(splits) != 0 (le validator zero-sum
    # n'est actif qu'à `confirmed`, S07.3) : la strategy retourne bien un draft.
    assert tx.state is TransactionState.DRAFT
    assert len({s.amount.currency for s in tx.splits}) == 1  # devise unique


@given(tx=transaction_draft_strategy(balanced=True))
@settings(max_examples=100)
def test_property_draft_balanced_can_confirm(tx: Transaction) -> None:
    # `balanced=True` ⇒ un draft « confirmable » : assert_zero_sum ne lève pas.
    assert tx.state is TransactionState.DRAFT
    assert_zero_sum(tx)  # no raise — somme nulle par construction


@given(tx=transaction_confirmed_strategy())
@settings(max_examples=100)
def test_property_confirmed_strategy_is_zero_sum(tx: Transaction) -> None:
    # Le `model_validator` a accepté la construction `confirmed` ⇒ zero-sum
    # garanti ; on le reconfronte à `assert_zero_sum` (no raise).
    assert tx.state is TransactionState.CONFIRMED
    assert_zero_sum(tx)


def test_strategies_importable_without_side_effect() -> None:
    # Contrat AC : les strategies sont importables sans effet de bord (le module
    # est déjà chargé ici ; on vérifie le contrat d'API public sans instancier ni
    # toucher de ressource externe — gabarit `test_accounts_strategies.py`).
    assert callable(strategies.money_strategy)
    assert callable(strategies.balanced_splits_strategy)
    assert callable(strategies.transaction_draft_strategy)
    assert callable(strategies.transaction_confirmed_strategy)
