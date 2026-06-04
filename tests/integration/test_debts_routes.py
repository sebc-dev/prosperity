"""Integration tests for the debts dashboard HTTP routes (S09.4, P09.4.2/P09.4.3).

Drives `GET /debts` and `GET /debts/by-counterparty` over httpx end to end. The
debt is materialised the real way — `POST /transactions/{tx_id}/share-requests`
(S09.3) — so the read path sees a production-shaped row.

Covers: 401 on both routes; bornage to the token; `direction` (all/owed_to_me/
owed_by_me); the `with` counterparty filter; the IDOR negative (a third party
sees nothing via `with`); debtor-side masking of `source_transaction_id` AND
`account_id` (and `materialization_trace` absent from the JSON) on BOTH routes;
the oriented `net_amount` (positive for the creditor, negative for the debtor).
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from backend.config import get_settings
from backend.modules.auth.service.jwt import issue_access_token
from tests.factories.sqlalchemy import CategoryFactory

_settings = get_settings()

TxFactoryBundle = Callable[[], Awaitable[tuple[type, type, type, type]]]

_TX_DATE = dt.date(2026, 3, 15)
_AMOUNT = 4000


def _bearer(user_id: uuid.UUID) -> dict[str, str]:
    return {"Authorization": f"Bearer {issue_access_token(user_id, settings=_settings)}"}


@dataclass
class _Scenario:
    alice_id: uuid.UUID  # creditor / owner of the source account
    bob_id: uuid.UUID  # debtor
    charlie_id: uuid.UUID  # unrelated third party
    account_id: uuid.UUID
    tx_id: uuid.UUID
    category_id: uuid.UUID


async def _seed(
    session: AsyncSession, factories: TxFactoryBundle, *, amount_cents: int = _AMOUNT
) -> _Scenario:
    user_factory, account_factory, tx_factory, _split_factory = await factories()

    def _do(_s: Session) -> _Scenario:
        alice = user_factory(email="alice@example.com")
        bob = user_factory(email="bob@example.com")
        charlie = user_factory(email="charlie@example.com")
        cat = CategoryFactory()
        account = account_factory(owner_id=alice.id, name="Alice perso")
        tx = tx_factory(
            account_id=account.id,
            created_by=alice.id,
            state="confirmed",
            category_id=cat.id,
            date=_TX_DATE,
            splits__amount_cents=amount_cents,
        )
        return _Scenario(alice.id, bob.id, charlie.id, account.id, tx.id, cat.id)

    return await session.run_sync(_do)


async def _materialise_debt(
    client: AsyncClient, scenario: _Scenario, *, short_label: str = "Courses"
) -> None:
    """Create the SR + Debt via the real POST route (Alice → Bob)."""
    resp = await client.post(
        f"/transactions/{scenario.tx_id}/share-requests",
        json={
            "requested_from": str(scenario.bob_id),
            "ratio": "1.0",
            "short_label": short_label,
        },
        headers=_bearer(scenario.alice_id),
    )
    assert resp.status_code == 201, resp.text


# ---------------------------------------------------------------------------
# GET /debts
# ---------------------------------------------------------------------------


async def test_get_debts_401_without_token(async_client: AsyncClient) -> None:
    resp = await async_client.get("/debts")
    assert resp.status_code == 401


async def test_get_debts_returns_token_user_debts(
    async_client: AsyncClient,
    household_singleton: AsyncSession,
    bound_transaction_factories: TxFactoryBundle,
) -> None:
    s = await _seed(household_singleton, bound_transaction_factories)
    await _materialise_debt(async_client, s, short_label="Restaurant")

    resp = await async_client.get("/debts", headers=_bearer(s.alice_id))
    assert resp.status_code == 200, resp.text
    items = resp.json()["items"]
    assert len(items) == 1
    item = items[0]
    assert item["from_user_id"] == str(s.bob_id)
    assert item["to_user_id"] == str(s.alice_id)
    assert item["amount_cents"] == _AMOUNT
    assert item["short_label"] == "Restaurant"
    assert item["category_id"] == str(s.category_id)
    assert item["date"] == _TX_DATE.isoformat()


async def test_get_debts_direction_all_owed_to_me_owed_by_me(
    async_client: AsyncClient,
    household_singleton: AsyncSession,
    bound_transaction_factories: TxFactoryBundle,
) -> None:
    s = await _seed(household_singleton, bound_transaction_factories)
    await _materialise_debt(async_client, s)

    async def _count(user_id: uuid.UUID, direction: str) -> int:
        resp = await async_client.get(
            "/debts", params={"direction": direction}, headers=_bearer(user_id)
        )
        assert resp.status_code == 200, resp.text
        return len(resp.json()["items"])

    assert await _count(s.alice_id, "all") == 1
    assert await _count(s.alice_id, "owed_to_me") == 1  # Alice is creditor
    assert await _count(s.alice_id, "owed_by_me") == 0
    assert await _count(s.bob_id, "all") == 1
    assert await _count(s.bob_id, "owed_to_me") == 0
    assert await _count(s.bob_id, "owed_by_me") == 1  # Bob is debtor


async def test_get_debts_with_counterparty_filters(
    async_client: AsyncClient,
    household_singleton: AsyncSession,
    bound_transaction_factories: TxFactoryBundle,
) -> None:
    s = await _seed(household_singleton, bound_transaction_factories)
    await _materialise_debt(async_client, s)

    with_bob = await async_client.get(
        "/debts", params={"with": str(s.bob_id)}, headers=_bearer(s.alice_id)
    )
    with_charlie = await async_client.get(
        "/debts", params={"with": str(s.charlie_id)}, headers=_bearer(s.alice_id)
    )
    assert len(with_bob.json()["items"]) == 1
    assert with_charlie.json()["items"] == []


async def test_get_debts_debtor_masks_source_tx_and_account(
    async_client: AsyncClient,
    household_singleton: AsyncSession,
    bound_transaction_factories: TxFactoryBundle,
) -> None:
    s = await _seed(household_singleton, bound_transaction_factories)
    await _materialise_debt(async_client, s)

    resp = await async_client.get("/debts", headers=_bearer(s.bob_id))
    assert resp.status_code == 200, resp.text
    [item] = resp.json()["items"]
    assert item["source_transaction_id"] is None
    assert item["account_id"] is None
    assert "materialization_trace" not in item
    # The debtor still gets their entitled context.
    assert item["category_id"] == str(s.category_id)
    assert item["date"] == _TX_DATE.isoformat()


async def test_get_debts_owner_sees_source_tx_and_account(
    async_client: AsyncClient,
    household_singleton: AsyncSession,
    bound_transaction_factories: TxFactoryBundle,
) -> None:
    s = await _seed(household_singleton, bound_transaction_factories)
    await _materialise_debt(async_client, s)

    resp = await async_client.get("/debts", headers=_bearer(s.alice_id))
    [item] = resp.json()["items"]
    assert item["source_transaction_id"] == str(s.tx_id)
    assert item["account_id"] == str(s.account_id)
    assert "materialization_trace" not in item


async def test_get_debts_idor_with_third_party(
    async_client: AsyncClient,
    household_singleton: AsyncSession,
    bound_transaction_factories: TxFactoryBundle,
) -> None:
    # Charlie (unrelated) asks for the Alice↔Bob pair via `with` → sees nothing.
    s = await _seed(household_singleton, bound_transaction_factories)
    await _materialise_debt(async_client, s)

    resp = await async_client.get(
        "/debts", params={"with": str(s.alice_id)}, headers=_bearer(s.charlie_id)
    )
    assert resp.status_code == 200
    assert resp.json()["items"] == []


async def test_get_debts_invalid_direction_422(
    async_client: AsyncClient,
    household_singleton: AsyncSession,
    bound_transaction_factories: TxFactoryBundle,
) -> None:
    s = await _seed(household_singleton, bound_transaction_factories)
    resp = await async_client.get(
        "/debts", params={"direction": "bogus"}, headers=_bearer(s.alice_id)
    )
    assert resp.status_code == 422


async def test_get_debts_direction_and_with_combined(
    async_client: AsyncClient,
    household_singleton: AsyncSession,
    bound_transaction_factories: TxFactoryBundle,
) -> None:
    s = await _seed(household_singleton, bound_transaction_factories)
    await _materialise_debt(async_client, s)

    # owed_to_me AND with=bob → the single Alice-creditor / Bob-counterparty debt.
    matching = await async_client.get(
        "/debts",
        params={"direction": "owed_to_me", "with": str(s.bob_id)},
        headers=_bearer(s.alice_id),
    )
    # owed_by_me AND with=bob → Alice is not a debtor here → empty.
    empty = await async_client.get(
        "/debts",
        params={"direction": "owed_by_me", "with": str(s.bob_id)},
        headers=_bearer(s.alice_id),
    )
    assert len(matching.json()["items"]) == 1
    assert empty.json()["items"] == []


async def test_get_debts_empty_for_user_without_debts(
    async_client: AsyncClient,
    household_singleton: AsyncSession,
    bound_transaction_factories: TxFactoryBundle,
) -> None:
    s = await _seed(household_singleton, bound_transaction_factories)
    await _materialise_debt(async_client, s)

    resp = await async_client.get("/debts", headers=_bearer(s.charlie_id))
    assert resp.status_code == 200
    assert resp.json()["items"] == []


# ---------------------------------------------------------------------------
# GET /debts/by-counterparty
# ---------------------------------------------------------------------------


async def test_by_counterparty_401_without_token(async_client: AsyncClient) -> None:
    resp = await async_client.get("/debts/by-counterparty")
    assert resp.status_code == 401


async def test_by_counterparty_aggregates_net_and_count(
    async_client: AsyncClient,
    household_singleton: AsyncSession,
    bound_transaction_factories: TxFactoryBundle,
) -> None:
    s = await _seed(household_singleton, bound_transaction_factories)
    await _materialise_debt(async_client, s)

    resp = await async_client.get("/debts/by-counterparty", headers=_bearer(s.alice_id))
    assert resp.status_code == 200, resp.text
    [row] = resp.json()["items"]
    assert row["user_id"] == str(s.bob_id)
    assert row["net_amount"] == _AMOUNT  # Bob owes Alice → positive for the creditor
    assert row["debts_count"] == 1


async def test_by_counterparty_net_oriented_for_debtor(
    async_client: AsyncClient,
    household_singleton: AsyncSession,
    bound_transaction_factories: TxFactoryBundle,
) -> None:
    s = await _seed(household_singleton, bound_transaction_factories)
    await _materialise_debt(async_client, s)

    resp = await async_client.get("/debts/by-counterparty", headers=_bearer(s.bob_id))
    assert resp.status_code == 200, resp.text
    [row] = resp.json()["items"]
    assert row["user_id"] == str(s.alice_id)
    assert row["net_amount"] == -_AMOUNT  # Bob owes Alice → negative for the debtor


async def test_by_counterparty_no_source_fields_leak(
    async_client: AsyncClient,
    household_singleton: AsyncSession,
    bound_transaction_factories: TxFactoryBundle,
) -> None:
    s = await _seed(household_singleton, bound_transaction_factories)
    await _materialise_debt(async_client, s)

    resp = await async_client.get("/debts/by-counterparty", headers=_bearer(s.bob_id))
    [row] = resp.json()["items"]
    for forbidden in ("source_transaction_id", "account_id", "materialization_trace"):
        assert forbidden not in row


async def test_by_counterparty_bounded_to_token(
    async_client: AsyncClient,
    household_singleton: AsyncSession,
    bound_transaction_factories: TxFactoryBundle,
) -> None:
    s = await _seed(household_singleton, bound_transaction_factories)
    await _materialise_debt(async_client, s)

    resp = await async_client.get("/debts/by-counterparty", headers=_bearer(s.charlie_id))
    assert resp.status_code == 200
    assert resp.json()["items"] == []


async def test_by_counterparty_empty_for_user_without_debts(
    async_client: AsyncClient,
    household_singleton: AsyncSession,
    bound_transaction_factories: TxFactoryBundle,
) -> None:
    s = await _seed(household_singleton, bound_transaction_factories)
    await _materialise_debt(async_client, s)

    resp = await async_client.get("/debts/by-counterparty", headers=_bearer(s.charlie_id))
    assert resp.status_code == 200
    assert resp.json()["items"] == []
