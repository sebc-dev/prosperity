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
from backend.modules.budget.public import BudgetError, CategoryError
from backend.modules.debts.public import (
    DebtCalculationError,
    DebtNotFoundError,
    SettlementServiceError,
    SettlementValidationError,
    ShareRequestError,
    ShareRequestNotFoundError,
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
    # `*NotFoundError` → `not_found` (uniforme, anti-oracle)
    (TransactionNotFoundError(uuid4()), "not_found"),
    (SplitNotFoundError(uuid4()), "not_found"),
    (ShareRequestNotFoundError("sr404"), "not_found"),
    (DebtNotFoundError("debt404"), "not_found"),
]


_IDS = [type(exc).__name__ for exc, _ in _CASES]


@pytest.mark.parametrize(("exc", "expected_code"), _CASES, ids=_IDS)
def test_known_exception_maps_to_code(exc: Exception, expected_code: str) -> None:
    error = to_write_error(exc)
    assert error is not None
    assert error.code == expected_code


def test_unknown_exception_maps_to_none() -> None:
    """Une exception HORS du domaine connu → `None` (le dispatcher la propage → 500, D-H)."""
    assert to_write_error(RuntimeError("boom")) is None
    assert to_write_error(ValueError("oops")) is None


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
