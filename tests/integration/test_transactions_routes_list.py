"""Integration tests for `GET /transactions` (S07.5, P07.5.4).

Drives the watertight, cursor-paginated list over httpx. The load-bearing
assertion (F03/D3) is that the listing is filtered by **membership**: a caller
sees only the transactions of accounts they can reach, the admin is NOT exempt,
and a new user gets an empty page. An explicit `?account_id=X` the caller cannot
reach is a **404** (D4), not a silent empty list. Filters `from`/`to`/`state` and
the `(date DESC, id DESC)` cursor pagination are exercised end to end.

Transactions are seeded via the bound factories; the route never calls
`get_household`, so no household-cache bracketing is needed.
"""

from __future__ import annotations

import base64
from collections.abc import Awaitable, Callable
from datetime import date
from uuid import UUID, uuid4

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from backend.config import get_settings
from backend.modules.auth.domain import UserRole
from backend.modules.auth.service.jwt import issue_access_token

_settings = get_settings()

TxFactoryBundle = Callable[[], Awaitable[tuple[type, type, type, type]]]


def _bearer(user_id: UUID) -> dict[str, str]:
    return {"Authorization": f"Bearer {issue_access_token(user_id, settings=_settings)}"}


def _make_cursor(cursor_date: date, tx_id: UUID) -> str:
    """Build an opaque cursor in the same `b64(date|id)` format the route emits.

    Replicated black-box (not imported from the route) so the test stays a client
    of the public HTTP contract rather than the private encoder.
    """
    return base64.urlsafe_b64encode(f"{cursor_date.isoformat()}|{tx_id}".encode()).decode()


def _ids(payload: dict[str, object]) -> list[str]:
    return [row["id"] for row in payload["items"]]  # type: ignore[index, union-attr]


async def test_list_only_accessible_accounts(
    async_client: AsyncClient,
    household_singleton: AsyncSession,
    bound_transaction_factories: TxFactoryBundle,
) -> None:
    user_factory, account_factory, tx_factory, _ = await bound_transaction_factories()

    def _seed(_s: Session) -> tuple[UUID, UUID]:
        owner = user_factory(email="l1@example.com")
        stranger = user_factory(email="s1@example.com")
        mine = account_factory(owner_id=owner.id, name="Mine")
        theirs = account_factory(owner_id=stranger.id, name="Theirs")
        my_tx = tx_factory(account_id=mine.id, created_by=owner.id, state="draft")
        tx_factory(account_id=theirs.id, created_by=stranger.id, state="draft")
        return owner.id, my_tx.id

    owner_id, my_tx_id = await household_singleton.run_sync(_seed)

    resp = await async_client.get("/transactions", headers=_bearer(owner_id))
    assert resp.status_code == 200, resp.text
    assert _ids(resp.json()) == [str(my_tx_id)]


async def test_list_admin_not_exempt(
    async_client: AsyncClient,
    household_singleton: AsyncSession,
    bound_transaction_factories: TxFactoryBundle,
) -> None:
    # F03/D3: the admin does not see another user's account's transactions.
    user_factory, account_factory, tx_factory, _ = await bound_transaction_factories()

    def _seed(_s: Session) -> UUID:
        admin = user_factory(email="adm3@example.com", role=UserRole.ADMIN)
        member = user_factory(email="mem3@example.com")
        acc = account_factory(owner_id=member.id, name="Member perso")
        tx_factory(account_id=acc.id, created_by=member.id, state="draft")
        return admin.id

    admin_id = await household_singleton.run_sync(_seed)

    resp = await async_client.get("/transactions", headers=_bearer(admin_id))
    assert resp.status_code == 200, resp.text
    assert resp.json()["items"] == []
    assert resp.json()["next_cursor"] is None


async def test_list_empty_for_new_user(
    async_client: AsyncClient,
    household_singleton: AsyncSession,
    bound_transaction_factories: TxFactoryBundle,
) -> None:
    user_factory, _, _, _ = await bound_transaction_factories()

    def _seed(_s: Session) -> UUID:
        return user_factory(email="new@example.com").id

    user_id = await household_singleton.run_sync(_seed)

    resp = await async_client.get("/transactions", headers=_bearer(user_id))
    assert resp.status_code == 200, resp.text
    assert resp.json()["items"] == []


async def test_list_account_id_filter(
    async_client: AsyncClient,
    household_singleton: AsyncSession,
    bound_transaction_factories: TxFactoryBundle,
) -> None:
    user_factory, account_factory, tx_factory, _ = await bound_transaction_factories()

    def _seed(_s: Session) -> tuple[UUID, UUID, UUID]:
        owner = user_factory(email="l2@example.com")
        a = account_factory(owner_id=owner.id, name="A")
        b = account_factory(owner_id=owner.id, name="B")
        a_tx = tx_factory(account_id=a.id, created_by=owner.id, state="draft")
        tx_factory(account_id=b.id, created_by=owner.id, state="draft")
        return owner.id, a.id, a_tx.id

    owner_id, a_id, a_tx_id = await household_singleton.run_sync(_seed)

    resp = await async_client.get(
        "/transactions", params={"account_id": str(a_id)}, headers=_bearer(owner_id)
    )
    assert resp.status_code == 200, resp.text
    assert _ids(resp.json()) == [str(a_tx_id)]


async def test_list_account_id_inaccessible_404(
    async_client: AsyncClient,
    household_singleton: AsyncSession,
    bound_transaction_factories: TxFactoryBundle,
) -> None:
    # D4: an explicit account_id the caller cannot reach → 404, not empty list.
    user_factory, account_factory, _, _ = await bound_transaction_factories()

    def _seed(_s: Session) -> tuple[UUID, UUID]:
        owner = user_factory(email="l3@example.com")
        stranger = user_factory(email="s3@example.com")
        account_factory(owner_id=owner.id, name="Mine")
        theirs = account_factory(owner_id=stranger.id, name="Theirs")
        return owner.id, theirs.id

    owner_id, theirs_id = await household_singleton.run_sync(_seed)

    resp = await async_client.get(
        "/transactions", params={"account_id": str(theirs_id)}, headers=_bearer(owner_id)
    )
    assert resp.status_code == 404, resp.text
    assert resp.json()["detail"] == "Transaction not found."


async def test_list_account_id_unknown_404(
    async_client: AsyncClient,
    household_singleton: AsyncSession,
    bound_transaction_factories: TxFactoryBundle,
) -> None:
    user_factory, account_factory, _, _ = await bound_transaction_factories()

    def _seed(_s: Session) -> UUID:
        owner = user_factory(email="l4@example.com")
        account_factory(owner_id=owner.id, name="Mine")
        return owner.id

    owner_id = await household_singleton.run_sync(_seed)

    resp = await async_client.get(
        "/transactions", params={"account_id": str(uuid4())}, headers=_bearer(owner_id)
    )
    assert resp.status_code == 404, resp.text


async def test_list_date_filters(
    async_client: AsyncClient,
    household_singleton: AsyncSession,
    bound_transaction_factories: TxFactoryBundle,
) -> None:
    # `from`/`to` are inclusive: a tx falling exactly on either bound is returned.
    # Seeding a tx ON each bound pins `>=`/`<=` (a `>`/`<` regression would drop them).
    user_factory, account_factory, tx_factory, _ = await bound_transaction_factories()

    def _seed(_s: Session) -> tuple[UUID, list[str]]:
        owner = user_factory(email="l5@example.com")
        acc = account_factory(owner_id=owner.id, name="Mine")
        tx_factory(account_id=acc.id, created_by=owner.id, state="draft", date=date(2026, 1, 1))
        low = tx_factory(
            account_id=acc.id, created_by=owner.id, state="draft", date=date(2026, 3, 1)
        )
        mid = tx_factory(
            account_id=acc.id, created_by=owner.id, state="draft", date=date(2026, 6, 15)
        )
        high = tx_factory(
            account_id=acc.id, created_by=owner.id, state="draft", date=date(2026, 9, 1)
        )
        tx_factory(account_id=acc.id, created_by=owner.id, state="draft", date=date(2026, 12, 31))
        # Expected (date DESC): high (== to), mid, low (== from).
        return owner.id, [str(high.id), str(mid.id), str(low.id)]

    owner_id, expected = await household_singleton.run_sync(_seed)

    resp = await async_client.get(
        "/transactions",
        params={"from": "2026-03-01", "to": "2026-09-01"},
        headers=_bearer(owner_id),
    )
    assert resp.status_code == 200, resp.text
    assert _ids(resp.json()) == expected


async def test_list_combined_filters(
    async_client: AsyncClient,
    household_singleton: AsyncSession,
    bound_transaction_factories: TxFactoryBundle,
    bound_category_factory: Callable[..., Awaitable[object]],
) -> None:
    # account_id + from/to + state applied together narrow to a single tx.
    user_factory, account_factory, tx_factory, split_factory = await bound_transaction_factories()
    category = await bound_category_factory(name="X")
    cat_id = category.id  # type: ignore[attr-defined]

    def _seed(_s: Session) -> tuple[UUID, UUID, UUID]:
        owner = user_factory(email="lc@example.com")
        a = account_factory(owner_id=owner.id, name="A")
        b = account_factory(owner_id=owner.id, name="B")

        def _confirmed(account_id: UUID, when: date) -> object:
            tx = tx_factory(
                account_id=account_id,
                created_by=owner.id,
                state="confirmed",
                splits=False,
                date=when,
            )
            split_factory(
                transaction_id=tx.id, account_id=account_id, amount_cents=-1000, category_id=cat_id
            )
            split_factory(
                transaction_id=tx.id, account_id=account_id, amount_cents=1000, category_id=cat_id
            )
            return tx

        # The target: account A, in range, confirmed.
        target = _confirmed(a.id, date(2026, 6, 1))
        # Decoys, each violating exactly one filter.
        _confirmed(b.id, date(2026, 6, 1))  # wrong account
        _confirmed(a.id, date(2026, 1, 1))  # out of range
        tx_factory(
            account_id=a.id, created_by=owner.id, state="draft", date=date(2026, 6, 2)
        )  # state
        return owner.id, a.id, target.id  # type: ignore[attr-defined]

    owner_id, a_id, target_id = await household_singleton.run_sync(_seed)

    resp = await async_client.get(
        "/transactions",
        params={
            "account_id": str(a_id),
            "from": "2026-03-01",
            "to": "2026-09-01",
            "state": "confirmed",
        },
        headers=_bearer(owner_id),
    )
    assert resp.status_code == 200, resp.text
    assert _ids(resp.json()) == [str(target_id)]


async def test_list_state_filter(
    async_client: AsyncClient,
    household_singleton: AsyncSession,
    bound_transaction_factories: TxFactoryBundle,
    bound_category_factory: Callable[..., Awaitable[object]],
) -> None:
    user_factory, account_factory, tx_factory, split_factory = await bound_transaction_factories()
    category = await bound_category_factory(name="X")
    cat_id = category.id  # type: ignore[attr-defined]

    def _seed(_s: Session) -> tuple[UUID, UUID]:
        owner = user_factory(email="l6@example.com")
        acc = account_factory(owner_id=owner.id, name="Mine")
        tx_factory(account_id=acc.id, created_by=owner.id, state="draft")
        confirmed = tx_factory(
            account_id=acc.id, created_by=owner.id, state="confirmed", splits=False
        )
        split_factory(
            transaction_id=confirmed.id, account_id=acc.id, amount_cents=-1000, category_id=cat_id
        )
        split_factory(
            transaction_id=confirmed.id, account_id=acc.id, amount_cents=1000, category_id=cat_id
        )
        return owner.id, confirmed.id

    owner_id, confirmed_id = await household_singleton.run_sync(_seed)

    resp = await async_client.get(
        "/transactions", params={"state": "confirmed"}, headers=_bearer(owner_id)
    )
    assert resp.status_code == 200, resp.text
    assert _ids(resp.json()) == [str(confirmed_id)]


async def test_list_cursor_pagination(
    async_client: AsyncClient,
    household_singleton: AsyncSession,
    bound_transaction_factories: TxFactoryBundle,
) -> None:
    # Seed 5 transactions on distinct dates; page with limit=2 → 3 pages,
    # no overlap, no gaps, stable (date DESC, id DESC) order.
    user_factory, account_factory, tx_factory, _ = await bound_transaction_factories()

    def _seed(_s: Session) -> tuple[UUID, list[str]]:
        owner = user_factory(email="l7@example.com")
        acc = account_factory(owner_id=owner.id, name="Mine")
        ids_desc: list[str] = []
        for day in range(1, 6):
            tx = tx_factory(
                account_id=acc.id, created_by=owner.id, state="draft", date=date(2026, 1, day)
            )
            ids_desc.append(str(tx.id))
        ids_desc.reverse()  # date DESC → day 5 first
        return owner.id, ids_desc

    owner_id, expected_order = await household_singleton.run_sync(_seed)

    collected: list[str] = []
    cursor: str | None = None
    pages = 0
    while True:
        params: dict[str, str | int] = {"limit": 2}
        if cursor is not None:
            params["cursor"] = cursor
        resp = await async_client.get("/transactions", params=params, headers=_bearer(owner_id))
        assert resp.status_code == 200, resp.text
        body = resp.json()
        collected.extend(_ids(body))
        pages += 1
        cursor = body["next_cursor"]
        if cursor is None:
            break
        assert pages < 10  # guard against an infinite loop

    assert collected == expected_order
    assert len(collected) == 5


async def test_list_cursor_does_not_widen_perimeter(
    async_client: AsyncClient,
    household_singleton: AsyncSession,
    bound_transaction_factories: TxFactoryBundle,
) -> None:
    # A well-formed cursor only moves the keyset offset; it never bypasses the
    # membership filter. A cursor pointing at a far-future row (with a random id)
    # still yields ONLY the caller's transactions, never a stranger's.
    user_factory, account_factory, tx_factory, _ = await bound_transaction_factories()

    def _seed(_s: Session) -> tuple[UUID, UUID]:
        owner = user_factory(email="lcs@example.com")
        stranger = user_factory(email="scs@example.com")
        mine = account_factory(owner_id=owner.id, name="Mine")
        theirs = account_factory(owner_id=stranger.id, name="Theirs")
        my_tx = tx_factory(
            account_id=mine.id, created_by=owner.id, state="draft", date=date(2026, 1, 1)
        )
        tx_factory(
            account_id=theirs.id, created_by=stranger.id, state="draft", date=date(2026, 1, 1)
        )
        return owner.id, my_tx.id

    owner_id, my_tx_id = await household_singleton.run_sync(_seed)

    cursor = _make_cursor(date(2030, 1, 1), uuid4())
    resp = await async_client.get(
        "/transactions", params={"cursor": cursor}, headers=_bearer(owner_id)
    )
    assert resp.status_code == 200, resp.text
    assert _ids(resp.json()) == [str(my_tx_id)]


async def test_list_malformed_cursor_422(
    async_client: AsyncClient,
    household_singleton: AsyncSession,
    bound_transaction_factories: TxFactoryBundle,
) -> None:
    user_factory, _, _, _ = await bound_transaction_factories()

    def _seed(_s: Session) -> UUID:
        return user_factory(email="l8@example.com").id

    user_id = await household_singleton.run_sync(_seed)

    resp = await async_client.get(
        "/transactions", params={"cursor": "not-a-valid-cursor!!!"}, headers=_bearer(user_id)
    )
    assert resp.status_code == 422, resp.text
    assert resp.json()["detail"] == "Malformed pagination cursor."


async def test_list_limit_over_max_422(
    async_client: AsyncClient,
    household_singleton: AsyncSession,
    bound_transaction_factories: TxFactoryBundle,
) -> None:
    user_factory, _, _, _ = await bound_transaction_factories()

    def _seed(_s: Session) -> UUID:
        return user_factory(email="l9@example.com").id

    user_id = await household_singleton.run_sync(_seed)

    resp = await async_client.get("/transactions", params={"limit": 101}, headers=_bearer(user_id))
    assert resp.status_code == 422, resp.text


async def test_list_401_anonymous(async_client: AsyncClient) -> None:
    resp = await async_client.get("/transactions")
    assert resp.status_code == 401
