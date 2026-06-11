"""Contrat de surface publique consommée par les sous-handlers sync (S13.4).

Les handlers appellent les services métier UNIQUEMENT via `*.public` (ADR 0014).
Ce verrou (DB-free) casse si un module retire de son `__all__` un write que le
handler consomme — un refactor de la surface publique deviendrait un échec de test
plutôt qu'un `AttributeError` à l'exécution du write upload handler."""

from __future__ import annotations

import backend.modules.accounts.public as accounts_public
import backend.modules.budget.public as budget_public
import backend.modules.debts.public as debts_public
import backend.modules.transactions.public as transactions_public


def test_transactions_public_exposes_writes_consumed() -> None:
    expected = {
        "create_draft",
        "add_split",
        "remove_split",
        "transition_to_planned",
        "transition_to_confirmed",
        "void",
        "update_editable_fields",
        "get_transaction",
    }
    assert expected <= set(transactions_public.__all__)


def test_accounts_public_exposes_writes_and_value_objects() -> None:
    expected = {
        "create_personal",
        "create_shared",
        "rename",
        "archive",
        "AccountType",
        "MemberShare",
    }
    assert expected <= set(accounts_public.__all__)


def test_budget_public_exposes_category_and_budget_writes() -> None:
    expected = {
        "create_category",
        "move_category",
        "update_category",
        "archive_category",
        "create_budget",
        "update_budget",
        "archive_budget",
        "PeriodKind",
        "Scope",
    }
    assert expected <= set(budget_public.__all__)


def test_debts_public_exposes_client_writes_only() -> None:
    expected = {
        "create_settlement",
        "create_share_request",
        "revoke_share_request",
        "SettlementType",
        "SettlementLineInput",
    }
    assert expected <= set(debts_public.__all__)
