"""Unit tests for `_project_debt` masking — the pure fail-safe (S09.4).

`_project_debt` masks `source_transaction_id` AND `account_id` for any reader who
is not the source-account owner. Ownership is recognised ONLY for
`origin == "personal_share_request"` (owner = creditor = `to_user_id`); every
other origin falls through to the default-deny branch of `_reader_owns_source`.

These cases lock the fail-safe **purely** (no DB), in particular the
default-deny: a future origin (`shared_account_overflow`, E11) cannot leak the
source fields before its own ownership logic exists. The integration suite
covers the happy path against Postgres; this file pins the branch logic itself.
"""

from __future__ import annotations

import datetime as dt
from uuid import UUID, uuid4

from backend.modules.debts.models import Debt
from backend.modules.debts.service.dashboard import (
    DebtWithContext,
    _project_debt,  # pyright: ignore[reportPrivateUsage]
)

_CREATED_AT = dt.datetime(2026, 1, 1, tzinfo=dt.UTC)


def _debt(*, frm: UUID, to: UUID, origin: str) -> Debt:
    """In-memory `Debt` (no session) carrying the fields `_project_debt` reads."""
    return Debt(
        from_user_id=frm,
        to_user_id=to,
        amount_cents=4000,
        currency="EUR",
        account_id=uuid4(),
        source_transaction_id=uuid4(),
        origin=origin,
        created_at=_CREATED_AT,
    )


def _project(debt: Debt, *, reader: UUID) -> DebtWithContext:
    return _project_debt(
        debt,
        reader_id=reader,
        requested_by=debt.to_user_id,
        short_label="x",
        category_id=None,
        date=None,
        remaining_cents=debt.amount_cents,
    )


def test_creditor_sees_source_fields_for_personal_share_request() -> None:
    creditor, debtor = uuid4(), uuid4()
    debt = _debt(frm=debtor, to=creditor, origin="personal_share_request")
    view = _project(debt, reader=creditor)
    assert view.source_transaction_id == debt.source_transaction_id
    assert view.account_id == debt.account_id


def test_debtor_is_masked_for_personal_share_request() -> None:
    creditor, debtor = uuid4(), uuid4()
    debt = _debt(frm=debtor, to=creditor, origin="personal_share_request")
    view = _project(debt, reader=debtor)
    assert view.source_transaction_id is None
    assert view.account_id is None


def test_unknown_origin_masks_even_the_creditor() -> None:
    # Fail-safe: an origin whose ownership logic does not exist yet (e.g. the E11
    # `shared_account_overflow`) must default-deny — even the creditor
    # (`to_user_id`) gets the source fields masked, never leaked by default.
    creditor, debtor = uuid4(), uuid4()
    debt = _debt(frm=debtor, to=creditor, origin="shared_account_overflow")
    view = _project(debt, reader=creditor)
    assert view.source_transaction_id is None
    assert view.account_id is None


def test_short_label_none_propagates() -> None:
    # The defensive `LEFT JOIN share_requests` can yield no active SR → a `None`
    # `short_label`. That branch is structurally unreachable via the real seed in
    # V1 (revoking an SR hard-deletes its Debt), so it is pinned here purely:
    # `_project_debt` propagates `None` rather than crashing.
    creditor, debtor = uuid4(), uuid4()
    debt = _debt(frm=debtor, to=creditor, origin="personal_share_request")
    view = _project_debt(
        debt,
        reader_id=creditor,
        requested_by=debt.to_user_id,
        short_label=None,
        category_id=None,
        date=None,
        remaining_cents=debt.amount_cents,
    )
    assert view.short_label is None
