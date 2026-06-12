"""Unit tests for `backend.modules.debts.public` cross-module surface (S09.3).

Pins the re-export contract: the share-request service entry points + their
typed error taxonomy are exposed, identical to the internal symbols (no stub
re-implementation), with no `__all__` drift or duplicates.
"""

from __future__ import annotations

from dataclasses import is_dataclass
from uuid import uuid4

import backend.modules.debts.public as debts_public
from backend.modules.debts import domain as _domain
from backend.modules.debts.public import (
    CrossHouseholdError,
    DebtCalculationError,
    DebtNotFoundError,
    DuplicateActiveShareRequestError,
    LinkedTransactionNotAccessibleError,
    LinkedTransactionNotConfirmedError,
    LinkedTransactionNotTransferError,
    OpenDebt,
    RequestedFromNotMemberError,
    SelfShareError,
    SettlementDebtNotAccessibleError,
    SettlementServiceError,
    SettlementValidationError,
    ShareRequestError,
    ShareRequestNotFoundError,
    SourceAccountNotShareableError,
    SourceTransactionNotConfirmedError,
    SourceTransactionNotFoundError,
    compute_remaining,
    create_settlement,
    create_share_request,
    list_open_debts_between,
    revoke_share_request,
)
from backend.modules.debts.service import dashboard as _dashboard
from backend.modules.debts.service import remaining as _remaining
from backend.modules.debts.service import settlement as _settlement
from backend.modules.debts.service import share_request as _service


def test_public_exports_exact_set() -> None:
    assert sorted(debts_public.__all__) == [
        "CounterpartyNet",
        "CrossHouseholdError",
        "DebtCalculationError",
        "DebtDirection",
        "DebtNotFoundError",
        "DebtWithContext",
        "DuplicateActiveShareRequestError",
        "LinkedTransactionNotAccessibleError",
        "LinkedTransactionNotConfirmedError",
        "LinkedTransactionNotTransferError",
        "OpenDebt",
        "RequestedFromNotMemberError",
        "SelfShareError",
        "SettlementDebtNotAccessibleError",
        "SettlementLineInput",
        "SettlementServiceError",
        "SettlementType",
        "SettlementValidationError",
        "ShareRequestError",
        "ShareRequestNotFoundError",
        "SourceAccountNotShareableError",
        "SourceTransactionNotConfirmedError",
        "SourceTransactionNotFoundError",
        "aggregate_by_counterparty",
        "compute_remaining",
        "create_settlement",
        "create_share_request",
        "list_debts_for_user",
        "list_open_debts_between",
        "materialize_overflow",
        "recompute_overflow_on_budget_event",
        "rematerialize_overflow_on_edit",
        "remove_overflow_on_void",
        "revoke_share_request",
    ]
    assert len(debts_public.__all__) == len(set(debts_public.__all__))


def test_public_symbols_are_callable_or_exceptions() -> None:
    assert callable(create_share_request)
    assert callable(revoke_share_request)
    # S10.3 remaining-balance primitives (server-only, consumed by S10.4/E11).
    assert callable(compute_remaining)
    assert callable(list_open_debts_between)
    assert is_dataclass(OpenDebt)
    assert issubclass(DebtNotFoundError, Exception)
    assert issubclass(ShareRequestError, Exception)
    for sub in (
        SourceTransactionNotFoundError,
        SourceAccountNotShareableError,
        SourceTransactionNotConfirmedError,
        RequestedFromNotMemberError,
        SelfShareError,
        DuplicateActiveShareRequestError,
        ShareRequestNotFoundError,
    ):
        assert issubclass(sub, ShareRequestError)


def test_settlement_service_surface() -> None:
    # S10.4 `create_settlement` + its access/state error taxonomy.
    assert callable(create_settlement)
    assert issubclass(SettlementServiceError, Exception)
    for sub in (
        SettlementDebtNotAccessibleError,
        LinkedTransactionNotAccessibleError,
        LinkedTransactionNotConfirmedError,
        LinkedTransactionNotTransferError,
    ):
        assert issubclass(sub, SettlementServiceError)
    # CrossHouseholdError is a SUB-case of "debt not accessible" → same 404.
    assert issubclass(CrossHouseholdError, SettlementDebtNotAccessibleError)


def test_validation_error_bases_exposed_for_sync_mapping() -> None:
    # S13.6 (P13.6.3) : `sync.service.errors` collapse ces bases en `validation_error`.
    # On les expose telles quelles depuis `debts.domain` (mêmes objets, pas de stub).
    assert debts_public.DebtCalculationError is _domain.DebtCalculationError
    assert debts_public.SettlementValidationError is _domain.SettlementValidationError
    assert issubclass(DebtCalculationError, Exception)
    assert issubclass(SettlementValidationError, Exception)


def test_error_codes_are_stable_and_pii_free() -> None:
    # `code` is the client channel (copied as-is, never `str(exc)`): pin it.
    assert ShareRequestError.code == "share_request_error"
    assert SourceTransactionNotFoundError.code == "source_transaction_not_found"
    assert SourceAccountNotShareableError.code == "source_account_not_shareable"
    assert SourceTransactionNotConfirmedError.code == "source_transaction_not_confirmed"
    assert RequestedFromNotMemberError.code == "requested_from_not_member"
    assert SelfShareError.code == "self_share"
    assert DuplicateActiveShareRequestError.code == "duplicate_active_share_request"
    assert ShareRequestNotFoundError.code == "share_request_not_found"
    # `DebtNotFoundError` (S10.3): stable `code` + the instance message NEVER
    # carries the `debt_id` (anti-PII / anti-enumeration — D3).
    assert DebtNotFoundError.code == "debt_not_found"
    a_debt_id = uuid4()
    assert str(a_debt_id) not in str(DebtNotFoundError("debt does not exist"))
    # S10.4 settlement-service codes: stable + PII-free (no UUID in the message).
    assert SettlementServiceError.code == "settlement_service_error"
    assert SettlementDebtNotAccessibleError.code == "settlement_debt_not_accessible"
    assert CrossHouseholdError.code == "cross_household_leak"
    assert LinkedTransactionNotAccessibleError.code == "linked_transaction_not_accessible"
    assert LinkedTransactionNotConfirmedError.code == "linked_transaction_not_confirmed"
    assert LinkedTransactionNotTransferError.code == "linked_transaction_not_transfer"


def test_public_names_are_identical_objects_to_internals() -> None:
    # Guards against a refactor that re-implements a stub in `public.py`
    # instead of re-exporting the real symbols from the service module.
    assert debts_public.create_share_request is _service.create_share_request
    assert debts_public.revoke_share_request is _service.revoke_share_request
    assert debts_public.ShareRequestError is _service.ShareRequestError
    assert debts_public.SourceTransactionNotFoundError is _service.SourceTransactionNotFoundError
    assert debts_public.SourceAccountNotShareableError is _service.SourceAccountNotShareableError
    assert (
        debts_public.SourceTransactionNotConfirmedError
        is _service.SourceTransactionNotConfirmedError
    )
    assert debts_public.RequestedFromNotMemberError is _service.RequestedFromNotMemberError
    assert debts_public.SelfShareError is _service.SelfShareError
    assert (
        debts_public.DuplicateActiveShareRequestError is _service.DuplicateActiveShareRequestError
    )
    assert debts_public.ShareRequestNotFoundError is _service.ShareRequestNotFoundError
    # The S09.4 read surface re-exports the real dashboard symbols (no stub).
    assert debts_public.list_debts_for_user is _dashboard.list_debts_for_user
    assert debts_public.aggregate_by_counterparty is _dashboard.aggregate_by_counterparty
    assert debts_public.DebtWithContext is _dashboard.DebtWithContext
    assert debts_public.CounterpartyNet is _dashboard.CounterpartyNet
    assert debts_public.DebtDirection is _dashboard.DebtDirection
    # The S10.3 remaining-balance primitives re-export the real symbols (no stub).
    assert debts_public.compute_remaining is _remaining.compute_remaining
    assert debts_public.list_open_debts_between is _remaining.list_open_debts_between
    assert debts_public.OpenDebt is _remaining.OpenDebt
    assert debts_public.DebtNotFoundError is _remaining.DebtNotFoundError
    # The S10.4 settlement service re-exports the real symbols (no stub).
    assert debts_public.create_settlement is _settlement.create_settlement
    assert debts_public.SettlementServiceError is _settlement.SettlementServiceError
    assert (
        debts_public.SettlementDebtNotAccessibleError
        is _settlement.SettlementDebtNotAccessibleError
    )
    assert debts_public.CrossHouseholdError is _settlement.CrossHouseholdError
    assert (
        debts_public.LinkedTransactionNotAccessibleError
        is _settlement.LinkedTransactionNotAccessibleError
    )
    assert (
        debts_public.LinkedTransactionNotConfirmedError
        is _settlement.LinkedTransactionNotConfirmedError
    )
    assert (
        debts_public.LinkedTransactionNotTransferError
        is _settlement.LinkedTransactionNotTransferError
    )
    # The S13.4 param-types consumed by the sync handlers re-export the real
    # `debts.domain` symbols (`SettlementLineInput` is a concrete class — no stub).
    assert debts_public.SettlementType is _domain.SettlementType
    assert debts_public.SettlementLineInput is _domain.SettlementLineInput
