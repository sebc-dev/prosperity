"""Unit tests for `backend.modules.debts.public` cross-module surface (S09.3).

Pins the re-export contract: the share-request service entry points + their
typed error taxonomy are exposed, identical to the internal symbols (no stub
re-implementation), with no `__all__` drift or duplicates.
"""

from __future__ import annotations

import backend.modules.debts.public as debts_public
from backend.modules.debts.public import (
    DuplicateActiveShareRequestError,
    RequestedFromNotMemberError,
    SelfShareError,
    ShareRequestError,
    ShareRequestNotFoundError,
    SourceAccountNotShareableError,
    SourceTransactionNotConfirmedError,
    SourceTransactionNotFoundError,
    create_share_request,
    revoke_share_request,
)
from backend.modules.debts.service import share_request as _service


def test_public_exports_exact_set() -> None:
    assert sorted(debts_public.__all__) == [
        "DuplicateActiveShareRequestError",
        "RequestedFromNotMemberError",
        "SelfShareError",
        "ShareRequestError",
        "ShareRequestNotFoundError",
        "SourceAccountNotShareableError",
        "SourceTransactionNotConfirmedError",
        "SourceTransactionNotFoundError",
        "create_share_request",
        "revoke_share_request",
    ]
    assert len(debts_public.__all__) == len(set(debts_public.__all__))


def test_public_symbols_are_callable_or_exceptions() -> None:
    assert callable(create_share_request)
    assert callable(revoke_share_request)
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
