"""Integration tests for the settlement HTTP routes (S10.4, P10.4.2/P10.4.3).

Drives `POST /settlements`, `GET /settlements?with=<user>` and
`GET /settlements/{id}` over httpx. `by_user_id` is always the token's user (D7),
never the body. Covers 201 for the 3 types (incl. a mono-USD happy path), the
4xx surface (404 anti-oracle, 422 invariants + Pydantic boundary), the
`extra="forbid"` anti-usurpation guard, the IDOR-bounded `with` filter, the
deterministic order, the D9 fully-settled-debt listing, and (P10.4.3) the detail
masking + per-debt RBAC filter.

Seeds via direct ORM inserts on `household_singleton`; routes run in their own
request session (savepoint mode) on the same connection, so a route's
commit-on-success is visible when reading back from `household_singleton`.
"""

from __future__ import annotations

import datetime as dt
import logging
import uuid
from collections.abc import Awaitable, Callable

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import get_settings
from backend.modules.accounts.domain import AccountType
from backend.modules.accounts.models import Account
from backend.modules.auth.models import User
from backend.modules.auth.service.jwt import issue_access_token
from backend.modules.debts.models import Debt, Settlement, SettlementLine
from backend.modules.debts.public import compute_remaining
from backend.modules.transactions.models import Split, Transaction

pytestmark = pytest.mark.usefixtures("household_singleton")

_settings = get_settings()
HOUSEHOLD_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
UserFactory = Callable[..., Awaitable[User]]


def _bearer(user_id: uuid.UUID) -> dict[str, str]:
    return {"Authorization": f"Bearer {issue_access_token(user_id, settings=_settings)}"}


async def _make_account(
    session: AsyncSession, owner_id: uuid.UUID, *, currency: str = "EUR"
) -> uuid.UUID:
    account = Account(
        name="Compte courant", type=AccountType.COURANT, currency=currency, owner_id=owner_id
    )
    session.add(account)
    await session.flush()
    return account.id


async def _make_transfer_tx(  # noqa: PLR0913 — keyword-only seed helper
    session: AsyncSession,
    *,
    account_a: uuid.UUID,
    account_b: uuid.UUID,
    created_by: uuid.UUID,
    amount_cents: int,
    currency: str = "EUR",
) -> uuid.UUID:
    tx = Transaction(
        account_id=account_a, date=dt.date(2026, 6, 1), state="confirmed", created_by=created_by
    )
    session.add(tx)
    await session.flush()
    session.add(
        Split(
            transaction_id=tx.id, account_id=account_a, amount_cents=-amount_cents,
            currency=currency, leg_role="funding",
        )
    )
    session.add(
        Split(
            transaction_id=tx.id, account_id=account_b, amount_cents=amount_cents,
            currency=currency, leg_role="funding",
        )
    )
    await session.flush()
    return tx.id


async def _make_external_tx(
    session: AsyncSession,
    *,
    account_id: uuid.UUID,
    created_by: uuid.UUID,
    amount_cents: int,
    currency: str = "EUR",
) -> uuid.UUID:
    tx = Transaction(
        account_id=account_id, date=dt.date(2026, 6, 1), state="confirmed", created_by=created_by
    )
    session.add(tx)
    await session.flush()
    for sign in (-amount_cents, amount_cents):
        session.add(
            Split(
                transaction_id=tx.id, account_id=account_id, amount_cents=sign,
                currency=currency, leg_role="funding",
            )
        )
    await session.flush()
    return tx.id


async def _make_debt(  # noqa: PLR0913 — keyword-only seed helper
    session: AsyncSession,
    *,
    from_user_id: uuid.UUID,
    to_user_id: uuid.UUID,
    account_id: uuid.UUID,
    source_transaction_id: uuid.UUID,
    amount_cents: int = 5000,
    currency: str = "EUR",
) -> Debt:
    debt = Debt(
        from_user_id=from_user_id, to_user_id=to_user_id, amount_cents=amount_cents,
        currency=currency, account_id=account_id, source_transaction_id=source_transaction_id,
        origin="personal_share_request",
    )
    session.add(debt)
    await session.flush()
    return debt


def _body(
    *,
    type_: str,
    lines: list[tuple[uuid.UUID, int]],
    linked_transaction_id: uuid.UUID | None,
    note: str | None = None,
    settled_at: str = "2026-06-03",
) -> dict[str, object]:
    body: dict[str, object] = {
        "type": type_,
        "settled_at": settled_at,
        "lines": [{"debt_id": str(d), "amount_cents": a} for d, a in lines],
    }
    if linked_transaction_id is not None:
        body["linked_transaction_id"] = str(linked_transaction_id)
    if note is not None:
        body["note"] = note
    return body


# ---------------------------------------------------------------------------
# POST happy paths (3 types) + token derivation
# ---------------------------------------------------------------------------


async def test_post_internal_transfer_201(
    async_client: AsyncClient, household_singleton: AsyncSession, bound_user_factory: UserFactory
) -> None:
    debtor, creditor = await bound_user_factory(), await bound_user_factory()
    acc_a = await _make_account(household_singleton, creditor.id)
    acc_b = await _make_account(household_singleton, creditor.id)
    tx_id = await _make_transfer_tx(
        household_singleton, account_a=acc_a, account_b=acc_b, created_by=creditor.id,
        amount_cents=5000,
    )
    debt = await _make_debt(
        household_singleton, from_user_id=debtor.id, to_user_id=creditor.id, account_id=acc_a,
        source_transaction_id=tx_id, amount_cents=5000,
    )
    resp = await async_client.post(
        "/settlements",
        json=_body(type_="internal_transfer", lines=[(debt.id, 5000)], linked_transaction_id=tx_id),
        headers=_bearer(creditor.id),
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["type"] == "internal_transfer"
    assert body["created_by"] == str(creditor.id)
    assert body["linked_transaction_id"] == str(tx_id)


async def test_post_external_transfer_201(
    async_client: AsyncClient, household_singleton: AsyncSession, bound_user_factory: UserFactory
) -> None:
    debtor, creditor = await bound_user_factory(), await bound_user_factory()
    acc = await _make_account(household_singleton, creditor.id)
    tx_id = await _make_external_tx(
        household_singleton, account_id=acc, created_by=creditor.id, amount_cents=4200
    )
    debt = await _make_debt(
        household_singleton, from_user_id=debtor.id, to_user_id=creditor.id, account_id=acc,
        source_transaction_id=tx_id, amount_cents=4200,
    )
    resp = await async_client.post(
        "/settlements",
        json=_body(type_="external_transfer", lines=[(debt.id, 4200)], linked_transaction_id=tx_id),
        headers=_bearer(creditor.id),
    )
    assert resp.status_code == 201, resp.text


async def test_post_virtual_201(
    async_client: AsyncClient, household_singleton: AsyncSession, bound_user_factory: UserFactory
) -> None:
    alice, bob = await bound_user_factory(), await bound_user_factory()
    acc = await _make_account(household_singleton, alice.id)
    tx_id = await _make_external_tx(
        household_singleton, account_id=acc, created_by=alice.id, amount_cents=1
    )
    b_to_a = await _make_debt(
        household_singleton, from_user_id=bob.id, to_user_id=alice.id, account_id=acc,
        source_transaction_id=tx_id, amount_cents=3000,
    )
    a_to_b = await _make_debt(
        household_singleton, from_user_id=alice.id, to_user_id=bob.id, account_id=acc,
        source_transaction_id=tx_id, amount_cents=3000,
    )
    resp = await async_client.post(
        "/settlements",
        json=_body(
            type_="virtual", lines=[(b_to_a.id, 3000), (a_to_b.id, 3000)],
            linked_transaction_id=None,
        ),
        headers=_bearer(alice.id),
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["linked_transaction_id"] is None


async def test_post_mono_usd_records_debt_currency_on_line(
    async_client: AsyncClient, household_singleton: AsyncSession, bound_user_factory: UserFactory
) -> None:
    # T-m1: a USD settlement → 201, and the line carries currency "USD" (copied
    # from the Debt, §3.2), not coincidentally EUR.
    debtor, creditor = await bound_user_factory(), await bound_user_factory()
    acc = await _make_account(household_singleton, creditor.id, currency="USD")
    tx_id = await _make_external_tx(
        household_singleton, account_id=acc, created_by=creditor.id, amount_cents=5000,
        currency="USD",
    )
    debt = await _make_debt(
        household_singleton, from_user_id=debtor.id, to_user_id=creditor.id, account_id=acc,
        source_transaction_id=tx_id, amount_cents=5000, currency="USD",
    )
    resp = await async_client.post(
        "/settlements",
        json=_body(type_="external_transfer", lines=[(debt.id, 5000)], linked_transaction_id=tx_id),
        headers=_bearer(creditor.id),
    )
    assert resp.status_code == 201, resp.text
    sid = uuid.UUID(resp.json()["id"])
    household_singleton.expire_all()
    line = (
        await household_singleton.execute(
            select(SettlementLine).where(SettlementLine.settlement_id == sid)
        )
    ).scalar_one()
    assert line.currency == "USD"


# ---------------------------------------------------------------------------
# Auth guard + anti-usurpation
# ---------------------------------------------------------------------------


async def test_post_without_token_401(async_client: AsyncClient) -> None:
    resp = await async_client.post(
        "/settlements",
        json=_body(type_="virtual", lines=[(uuid.uuid4(), 1000)], linked_transaction_id=None),
    )
    assert resp.status_code == 401


async def test_post_rejects_smuggled_by_user_id_422(
    async_client: AsyncClient, household_singleton: AsyncSession, bound_user_factory: UserFactory
) -> None:
    debtor, creditor = await bound_user_factory(), await bound_user_factory()
    acc = await _make_account(household_singleton, creditor.id)
    tx_id = await _make_external_tx(
        household_singleton, account_id=acc, created_by=creditor.id, amount_cents=1
    )
    debt = await _make_debt(
        household_singleton, from_user_id=debtor.id, to_user_id=creditor.id, account_id=acc,
        source_transaction_id=tx_id,
    )
    body = _body(type_="virtual", lines=[(debt.id, 1000)], linked_transaction_id=None)
    body["by_user_id"] = str(debtor.id)  # smuggled → extra="forbid"
    resp = await async_client.post("/settlements", json=body, headers=_bearer(creditor.id))
    assert resp.status_code == 422, resp.text


async def test_post_created_by_is_token_not_body(
    async_client: AsyncClient, household_singleton: AsyncSession, bound_user_factory: UserFactory
) -> None:
    debtor, creditor = await bound_user_factory(), await bound_user_factory()
    acc = await _make_account(household_singleton, creditor.id)
    tx_id = await _make_external_tx(
        household_singleton, account_id=acc, created_by=creditor.id, amount_cents=1000
    )
    debt = await _make_debt(
        household_singleton, from_user_id=debtor.id, to_user_id=creditor.id, account_id=acc,
        source_transaction_id=tx_id,
    )
    resp = await async_client.post(
        "/settlements",
        json=_body(type_="external_transfer", lines=[(debt.id, 1000)], linked_transaction_id=tx_id),
        headers=_bearer(creditor.id),
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["created_by"] == str(creditor.id)


# ---------------------------------------------------------------------------
# 4xx surface (404 anti-oracle + 422 invariants + Pydantic boundary)
# ---------------------------------------------------------------------------


async def test_post_unknown_debt_404(
    async_client: AsyncClient, household_singleton: AsyncSession, bound_user_factory: UserFactory
) -> None:
    creditor = await bound_user_factory()
    resp = await async_client.post(
        "/settlements",
        json=_body(type_="virtual", lines=[(uuid.uuid4(), 1000)], linked_transaction_id=None),
        headers=_bearer(creditor.id),
    )
    assert resp.status_code == 404, resp.text


async def test_post_caller_not_party_404(
    async_client: AsyncClient, household_singleton: AsyncSession, bound_user_factory: UserFactory
) -> None:
    debtor, creditor, stranger = (
        await bound_user_factory(),
        await bound_user_factory(),
        await bound_user_factory(),
    )
    acc = await _make_account(household_singleton, creditor.id)
    tx_id = await _make_external_tx(
        household_singleton, account_id=acc, created_by=creditor.id, amount_cents=1
    )
    debt = await _make_debt(
        household_singleton, from_user_id=debtor.id, to_user_id=creditor.id, account_id=acc,
        source_transaction_id=tx_id,
    )
    resp = await async_client.post(
        "/settlements",
        json=_body(type_="virtual", lines=[(debt.id, 1000)], linked_transaction_id=None),
        headers=_bearer(stranger.id),
    )
    assert resp.status_code == 404, resp.text


async def test_post_unknown_linked_tx_404(
    async_client: AsyncClient, household_singleton: AsyncSession, bound_user_factory: UserFactory
) -> None:
    debtor, creditor = await bound_user_factory(), await bound_user_factory()
    acc = await _make_account(household_singleton, creditor.id)
    tx_id = await _make_external_tx(
        household_singleton, account_id=acc, created_by=creditor.id, amount_cents=1
    )
    debt = await _make_debt(
        household_singleton, from_user_id=debtor.id, to_user_id=creditor.id, account_id=acc,
        source_transaction_id=tx_id,
    )
    resp = await async_client.post(
        "/settlements",
        json=_body(
            type_="external_transfer", lines=[(debt.id, 1000)],
            linked_transaction_id=uuid.uuid4(),
        ),
        headers=_bearer(creditor.id),
    )
    assert resp.status_code == 404, resp.text


async def test_post_non_confirmed_tx_422(
    async_client: AsyncClient, household_singleton: AsyncSession, bound_user_factory: UserFactory
) -> None:
    debtor, creditor = await bound_user_factory(), await bound_user_factory()
    acc_a = await _make_account(household_singleton, creditor.id)
    acc_b = await _make_account(household_singleton, creditor.id)
    tx = Transaction(
        account_id=acc_a, date=dt.date(2026, 6, 1), state="draft", created_by=creditor.id
    )
    household_singleton.add(tx)
    await household_singleton.flush()
    for acc, sign in ((acc_a, -5000), (acc_b, 5000)):
        household_singleton.add(
            Split(
                transaction_id=tx.id, account_id=acc, amount_cents=sign, currency="EUR",
                leg_role="funding",
            )
        )
    await household_singleton.flush()
    debt = await _make_debt(
        household_singleton, from_user_id=debtor.id, to_user_id=creditor.id, account_id=acc_a,
        source_transaction_id=tx.id, amount_cents=5000,
    )
    resp = await async_client.post(
        "/settlements",
        json=_body(type_="internal_transfer", lines=[(debt.id, 5000)], linked_transaction_id=tx.id),
        headers=_bearer(creditor.id),
    )
    assert resp.status_code == 422, resp.text


async def test_post_over_settlement_422(
    async_client: AsyncClient, household_singleton: AsyncSession, bound_user_factory: UserFactory
) -> None:
    debtor, creditor = await bound_user_factory(), await bound_user_factory()
    acc = await _make_account(household_singleton, creditor.id)
    tx_id = await _make_external_tx(
        household_singleton, account_id=acc, created_by=creditor.id, amount_cents=1
    )
    debt = await _make_debt(
        household_singleton, from_user_id=debtor.id, to_user_id=creditor.id, account_id=acc,
        source_transaction_id=tx_id, amount_cents=5000,
    )
    resp = await async_client.post(
        "/settlements",
        json=_body(type_="virtual", lines=[(debt.id, 8000)], linked_transaction_id=None),
        headers=_bearer(creditor.id),
    )
    assert resp.status_code == 422, resp.text


@pytest.mark.parametrize(
    ("type_", "linked"),
    [("virtual", True), ("external_transfer", False)],
)
async def test_post_link_type_mismatch_422_at_boundary(
    async_client: AsyncClient,
    bound_user_factory: UserFactory,
    type_: str,
    linked: bool,
) -> None:
    # `_link_matches_type`: virtual MUST NOT carry a link; non-virtual MUST. Both
    # rejected at the Pydantic boundary (422), before the service.
    creditor = await bound_user_factory()
    body = _body(
        type_=type_,
        lines=[(uuid.uuid4(), 1000)],
        linked_transaction_id=uuid.uuid4() if linked else None,
    )
    resp = await async_client.post("/settlements", json=body, headers=_bearer(creditor.id))
    assert resp.status_code == 422, resp.text


@pytest.mark.parametrize("note", ["with\nnewline", "tab\there", "ctrl\x07bell"])
async def test_post_note_control_chars_422(
    async_client: AsyncClient, bound_user_factory: UserFactory, note: str
) -> None:
    creditor = await bound_user_factory()
    body = _body(type_="virtual", lines=[(uuid.uuid4(), 1000)], linked_transaction_id=None)
    body["note"] = note
    resp = await async_client.post("/settlements", json=body, headers=_bearer(creditor.id))
    assert resp.status_code == 422, resp.text


@pytest.mark.parametrize(
    ("mutate", "expect"),
    [
        ("zero_amount", 422),
        ("empty_lines", 422),
        ("note_501", 422),
    ],
)
async def test_post_pydantic_edge_cases(
    async_client: AsyncClient, bound_user_factory: UserFactory, mutate: str, expect: int
) -> None:
    creditor = await bound_user_factory()
    body = _body(type_="virtual", lines=[(uuid.uuid4(), 1000)], linked_transaction_id=None)
    if mutate == "zero_amount":
        body["lines"] = [{"debt_id": str(uuid.uuid4()), "amount_cents": 0}]
    elif mutate == "empty_lines":
        body["lines"] = []
    elif mutate == "note_501":
        body["note"] = "x" * 501
    resp = await async_client.post("/settlements", json=body, headers=_bearer(creditor.id))
    assert resp.status_code == expect, resp.text


async def test_post_blank_note_normalised_to_none(
    async_client: AsyncClient, household_singleton: AsyncSession, bound_user_factory: UserFactory
) -> None:
    debtor, creditor = await bound_user_factory(), await bound_user_factory()
    acc = await _make_account(household_singleton, creditor.id)
    tx_id = await _make_external_tx(
        household_singleton, account_id=acc, created_by=creditor.id, amount_cents=1000
    )
    debt = await _make_debt(
        household_singleton, from_user_id=debtor.id, to_user_id=creditor.id, account_id=acc,
        source_transaction_id=tx_id,
    )
    body = _body(
        type_="external_transfer", lines=[(debt.id, 1000)], linked_transaction_id=tx_id, note="   "
    )
    resp = await async_client.post("/settlements", json=body, headers=_bearer(creditor.id))
    assert resp.status_code == 201, resp.text
    assert resp.json()["note"] is None


async def test_post_failure_logs_no_pii(
    async_client: AsyncClient,
    household_singleton: AsyncSession,
    bound_user_factory: UserFactory,
    caplog: pytest.LogCaptureFixture,
) -> None:
    # S-M5: a failed POST logs only the exception name + PII-free code — never the
    # note, an amount, or a debt UUID.
    debtor, creditor = await bound_user_factory(), await bound_user_factory()
    acc = await _make_account(household_singleton, creditor.id)
    tx_id = await _make_external_tx(
        household_singleton, account_id=acc, created_by=creditor.id, amount_cents=1
    )
    debt = await _make_debt(
        household_singleton, from_user_id=debtor.id, to_user_id=creditor.id, account_id=acc,
        source_transaction_id=tx_id, amount_cents=5000,
    )
    secret_note = "secretmemo12345"
    with caplog.at_level(logging.INFO):
        resp = await async_client.post(
            "/settlements",
            json=_body(
                type_="virtual", lines=[(debt.id, 8000)], linked_transaction_id=None,
                note=secret_note,
            ),
            headers=_bearer(creditor.id),
        )
    assert resp.status_code == 422
    blob = "\n".join(r.getMessage() + str(getattr(r, "code", "")) for r in caplog.records)
    assert secret_note not in blob
    assert "8000" not in blob
    assert str(debt.id) not in blob


# ---------------------------------------------------------------------------
# GET /settlements?with — IDOR bounding, order, D9
# ---------------------------------------------------------------------------


async def _virtual_settlement_on(
    session: AsyncSession, *, debt: Debt, created_by: uuid.UUID, amount: int,
    settled_at: dt.date = dt.date(2026, 6, 3),
) -> Settlement:
    s = Settlement(
        household_id=HOUSEHOLD_ID, created_by=created_by, type="virtual",
        linked_transaction_id=None, settled_at=settled_at,
    )
    session.add(s)
    await session.flush()
    session.add(
        SettlementLine(settlement_id=s.id, debt_id=debt.id, amount_cents=amount, currency="EUR")
    )
    await session.flush()
    return s


async def test_list_idor_bounded_by_token(
    async_client: AsyncClient, household_singleton: AsyncSession, bound_user_factory: UserFactory
) -> None:
    # A settlement between two third parties (caller party to neither) never
    # surfaces, even by passing one of them as `with` (anti-IDOR).
    alice, bob, carol = (
        await bound_user_factory(),
        await bound_user_factory(),
        await bound_user_factory(),
    )
    acc = await _make_account(household_singleton, bob.id)
    tx_id = await _make_external_tx(
        household_singleton, account_id=acc, created_by=bob.id, amount_cents=1
    )
    bob_carol = await _make_debt(
        household_singleton, from_user_id=bob.id, to_user_id=carol.id, account_id=acc,
        source_transaction_id=tx_id, amount_cents=5000,
    )
    await _virtual_settlement_on(
        household_singleton, debt=bob_carol, created_by=bob.id, amount=2000
    )

    resp = await async_client.get(f"/settlements?with={carol.id}", headers=_bearer(alice.id))
    assert resp.status_code == 200, resp.text
    assert resp.json()["items"] == []


async def test_list_includes_fully_settled_debt(
    async_client: AsyncClient, household_singleton: AsyncSession, bound_user_factory: UserFactory
) -> None:
    # D9: a debt apaid to remaining 0 still surfaces its settlement (a
    # `list_open_debts_between`-based bounding would drop it).
    debtor, creditor = await bound_user_factory(), await bound_user_factory()
    acc = await _make_account(household_singleton, creditor.id)
    tx_id = await _make_external_tx(
        household_singleton, account_id=acc, created_by=creditor.id, amount_cents=1
    )
    debt = await _make_debt(
        household_singleton, from_user_id=debtor.id, to_user_id=creditor.id, account_id=acc,
        source_transaction_id=tx_id, amount_cents=5000,
    )
    s = await _virtual_settlement_on(
        household_singleton, debt=debt, created_by=creditor.id, amount=5000
    )
    assert await compute_remaining(household_singleton, debt_id=debt.id) == 0
    resp = await async_client.get(f"/settlements?with={debtor.id}", headers=_bearer(creditor.id))
    assert resp.status_code == 200, resp.text
    assert [item["id"] for item in resp.json()["items"]] == [str(s.id)]


async def test_list_deterministic_order(
    async_client: AsyncClient, household_singleton: AsyncSession, bound_user_factory: UserFactory
) -> None:
    # settled_at DESC, then id. Two distinct dates + two same-date settlements.
    debtor, creditor = await bound_user_factory(), await bound_user_factory()
    acc = await _make_account(household_singleton, creditor.id)
    tx_id = await _make_external_tx(
        household_singleton, account_id=acc, created_by=creditor.id, amount_cents=1
    )
    debt = await _make_debt(
        household_singleton, from_user_id=debtor.id, to_user_id=creditor.id, account_id=acc,
        source_transaction_id=tx_id, amount_cents=100000,
    )
    s_old = await _virtual_settlement_on(
        household_singleton, debt=debt, created_by=creditor.id, amount=10,
        settled_at=dt.date(2026, 6, 1),
    )
    s_new_a = await _virtual_settlement_on(
        household_singleton, debt=debt, created_by=creditor.id, amount=10,
        settled_at=dt.date(2026, 6, 5),
    )
    s_new_b = await _virtual_settlement_on(
        household_singleton, debt=debt, created_by=creditor.id, amount=10,
        settled_at=dt.date(2026, 6, 5),
    )
    resp = await async_client.get(f"/settlements?with={debtor.id}", headers=_bearer(creditor.id))
    assert resp.status_code == 200, resp.text
    ids = [item["id"] for item in resp.json()["items"]]
    same_date_tail = sorted([str(s_new_a.id), str(s_new_b.id)])
    assert ids == [*same_date_tail, str(s_old.id)]
