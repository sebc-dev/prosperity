"""Table de correspondance exception domaine → `WriteError` typé (S13.6 / P13.6.3).

`to_write_error` est la SOURCE UNIQUE (ADR 0014) : un cas par CATÉGORIE de code, plus
les verrous transverses — message STATIQUE (no leak, Sécu F2), vocabulaire FERMÉ
(`WriteErrorCode` `Literal`), et inconnue → `None` (→ 500, D-H). Unitaire et DB-free :
on instancie les exceptions directement (pas de chemin métier — couvert en intégration
par `test_sync_dispatcher_errors`).
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from pydantic import ValidationError

from backend.modules.accounts.public import AccountValidationError
from backend.modules.budget.domain import CategoryNotFoundError
from backend.modules.budget.public import BudgetError, CategoryError
from backend.modules.debts.public import (
    CrossHouseholdError,
    DebtCalculationError,
    DebtNotFoundError,
    LinkedTransactionNotAccessibleError,
    SettlementDebtNotAccessibleError,
    SettlementServiceError,
    SettlementValidationError,
    ShareRequestError,
    ShareRequestNotFoundError,
    SourceTransactionNotFoundError,
)
from backend.modules.sync.schemas import WriteError
from backend.modules.sync.service.errors import to_write_error
from backend.modules.transactions.public import (
    ImmutableFieldViolation,
    InvalidStateTransitionError,
    MultipleFundingLegsError,
    SplitNotFoundError,
    TransactionError,
    TransactionNotFoundError,
    TransactionState,
    UnbalancedTransactionError,
    UncategorizedExpenseError,
)

# (instance d'exception, code wire attendu) — un cas par CATÉGORIE (ADR 0014).
_CASES: list[tuple[Exception, str]] = [
    # familles `transactions` dont le `.code` est DÉJÀ dans le vocabulaire fermé
    (ImmutableFieldViolation("splits"), "immutable_field_violation"),
    (UnbalancedTransactionError("déséquilibrée"), "unbalanced_transaction"),
    (
        InvalidStateTransitionError(TransactionState.VOID, TransactionState.CONFIRMED),
        "invalid_state_transition",
    ),
    (UncategorizedExpenseError(uuid4()), "uncategorized_expense"),
    # base `TransactionError` + `MultipleFundingLegsError` (hors vocab) → générique
    (MultipleFundingLegsError(uuid4()), "validation_error"),
    (TransactionError("générique"), "validation_error"),
    # familles de validation des autres modules → collapse `validation_error`
    (AccountValidationError("ratios"), "validation_error"),
    (CategoryError("cycle"), "validation_error"),
    (BudgetError("contrib"), "validation_error"),
    (ShareRequestError("sr"), "validation_error"),
    (SettlementValidationError("overpay"), "validation_error"),
    (SettlementServiceError("svc"), "validation_error"),
    (DebtCalculationError("calc"), "validation_error"),
    # `*NotFoundError` de ressource NON SENSIBLE → `not_found` (uniforme, anti-oracle)
    (TransactionNotFoundError(uuid4()), "not_found"),
    (SplitNotFoundError(uuid4()), "not_found"),
    (ShareRequestNotFoundError("sr404"), "not_found"),
    (DebtNotFoundError("debt404"), "not_found"),
]

# Sous-classes à nom « NotFound/NotAccessible » qui encodent une existence/accès
# CROSS-HOUSEHOLD : elles mappent DÉLIBÉRÉMENT en `validation_error`, PAS `not_found`
# (le domaine est déjà 404-first/anti-oracle en amont — les promouvoir rouvrirait
# l'oracle d'existence/accès, cf. docstring de `service/errors.py`). Ce verrou fige
# le choix : un futur refactor qui les déplacerait en `not_found` casse ce test.
_ANTI_ORACLE_CASES: list[tuple[Exception, str]] = [
    (CategoryNotFoundError("cat404"), "validation_error"),
    (SourceTransactionNotFoundError("src404"), "validation_error"),
    (SettlementDebtNotAccessibleError("debt404"), "validation_error"),
    (CrossHouseholdError("leak"), "validation_error"),
    (LinkedTransactionNotAccessibleError("tx404"), "validation_error"),
]


_IDS = [type(exc).__name__ for exc, _ in _CASES]
_ANTI_ORACLE_IDS = [type(exc).__name__ for exc, _ in _ANTI_ORACLE_CASES]


@pytest.mark.parametrize(("exc", "expected_code"), _CASES, ids=_IDS)
def test_known_exception_maps_to_code(exc: Exception, expected_code: str) -> None:
    error = to_write_error(exc)
    assert error is not None
    assert error.code == expected_code


@pytest.mark.parametrize(("exc", "expected_code"), _ANTI_ORACLE_CASES, ids=_ANTI_ORACLE_IDS)
def test_sensitive_notfound_subclasses_stay_validation_error(
    exc: Exception, expected_code: str
) -> None:
    """Les sous-classes existence/accès cross-household NE doivent PAS être promues en
    `not_found` : elles restent `validation_error` (anti-oracle, choix délibéré). Ce test
    échoue si quelqu'un les ajoute naïvement à la branche `not_found`."""
    error = to_write_error(exc)
    assert error is not None
    assert error.code == expected_code
    assert error.code != "not_found"


def _all_subclasses(root: type) -> set[type]:
    """Sous-classes transitives de `root` actuellement chargées."""
    seen: set[type] = set()
    stack = [root]
    while stack:
        for sub in stack.pop().__subclasses__():
            if sub not in seen:
                seen.add(sub)
                stack.append(sub)
    return seen


# Racines des familles d'exceptions CONNUES de `to_write_error`. Toute sous-classe
# réelle (chargée via les imports `*.public`/`*.domain`) DOIT être mappée — jamais
# fuir en `None` → 500 (un 500 sur une erreur domaine = faux négatif côté client).
_KNOWN_FAMILY_ROOTS: list[type[Exception]] = [
    TransactionError,
    AccountValidationError,
    CategoryError,
    BudgetError,
    ShareRequestError,
    SettlementValidationError,
    SettlementServiceError,
    DebtCalculationError,
    DebtNotFoundError,
]
_KNOWN_FAMILY_SUBCLASSES = sorted(
    {sub for root in _KNOWN_FAMILY_ROOTS for sub in _all_subclasses(root)},
    key=lambda c: c.__name__,
)


@pytest.mark.parametrize(
    "cls", _KNOWN_FAMILY_SUBCLASSES, ids=[c.__name__ for c in _KNOWN_FAMILY_SUBCLASSES]
)
def test_no_known_family_subclass_leaks_to_500(cls: type[Exception]) -> None:
    """Balayage exhaustif : AUCUNE sous-classe d'une famille connue ne mappe en `None`
    (→ 500). `cls.__new__(cls)` instancie sans `__init__` (le mapping ne lit que le TYPE +
    le `.code` ClassVar). Garde-fou contre une sous-classe future hors-arbre du `match`."""
    exc = cls.__new__(cls)
    assert to_write_error(exc) is not None, f"{cls.__name__} fuit en None → 500"


def test_unknown_exception_maps_to_none() -> None:
    """Une exception HORS du domaine connu → `None` (le dispatcher la propage → 500, D-H).

    Inclut `pydantic.ValidationError` (payload mal formé, étape 3) : le mapping ne
    traite QUE les exceptions domaine — une erreur de validation wire doit propager → 500
    (D-I), jamais être ack-ée comme une erreur récupérable."""
    assert to_write_error(RuntimeError("boom")) is None
    assert to_write_error(ValueError("oops")) is None
    try:
        WriteError(code="nope", message="x")  # type: ignore[arg-type]
    except ValidationError as exc:
        assert to_write_error(exc) is None
    else:  # pragma: no cover — la ligne ci-dessus DOIT lever
        pytest.fail("WriteError(code='nope') aurait dû lever une ValidationError")


def test_message_is_static_and_leaks_no_detail() -> None:
    """`message` est une CONSTANTE statique partagée par tous les codes — jamais
    `str(exc)` (qui peut porter un id, un champ, une devise…). On le prouve sans
    coupler au littéral : tous les messages sont IDENTIQUES, non vides, et ne
    contiennent aucun `str(exc)` (séparation code/message, fuite bornée — Sécu F2)."""
    errors = [to_write_error(exc) for exc, _ in _CASES]
    assert all(e is not None for e in errors)
    messages = {e.message for e in errors if e is not None}
    assert len(messages) == 1  # un seul message statique, partagé
    (message,) = messages
    assert message  # non vide
    for exc, _ in _CASES:
        assert str(exc) not in message  # aucun détail interne reporté


def test_write_error_code_is_a_closed_literal() -> None:
    """Le vocabulaire wire est FERMÉ : un code hors `WriteErrorCode` est un 422 Pydantic."""
    WriteError(code="validation_error", message="ok")  # un code valide passe
    with pytest.raises(ValidationError):
        WriteError(code="nope", message="x")  # type: ignore[arg-type]
