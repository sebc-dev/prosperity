"""Integration tests for the debts HTTP routes (S09.3, P09.3.3).

Drives `POST /transactions/{tx_id}/share-requests` and
`DELETE /share-requests/{id}` over httpx. `by_user_id` is always the token's user
(D7), never the body. Covers 201 + the full 4xx surface (404 anti-oracle, 422 per
rejection incl. the whitelist, 409 duplicate), 401 on BOTH routers, DELETE 204
(idempotent), and IDOR (revoke another user's SR → 404).

Seeds via `bound_transaction_factories` on `household_singleton`; the route runs
in its own request session (savepoint mode) on the same connection, so its
commit-on-success is visible when reading back from `household_singleton`.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from decimal import Decimal

from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from backend.config import get_settings
from backend.modules.accounts.models import AccountMember
from backend.modules.auth.service.jwt import issue_access_token
from backend.modules.debts.models import Debt, ShareRequest
from tests.factories.sqlalchemy import CategoryFactory

_settings = get_settings()

TxFactoryBundle = Callable[[], Awaitable[tuple[type, type, type, type]]]
_Leg = tuple[int, bool]


def _bearer(user_id: uuid.UUID) -> dict[str, str]:
    return {"Authorization": f"Bearer {issue_access_token(user_id, settings=_settings)}"}


@dataclass
class _Scenario:
    alice_id: uuid.UUID
    bob_id: uuid.UUID
    account_id: uuid.UUID
    tx_id: uuid.UUID


async def _seed(  # noqa: PLR0913 — keyword-only scenario knobs
    session: AsyncSession,
    factories: TxFactoryBundle,
    *,
    legs: list[_Leg],
    state: str = "confirmed",
    personal: bool = True,
    tx_owner_is_alice: bool = True,
    bob_disabled: bool = False,
) -> _Scenario:
    user_factory, account_factory, tx_factory, split_factory = await factories()

    def _do(sync_session: Session) -> _Scenario:
        alice = user_factory(email="alice@example.com")
        bob_kwargs: dict[str, object] = {"email": "bob@example.com"}
        if bob_disabled:
            bob_kwargs["disabled_at"] = dt.datetime(2026, 1, 1, tzinfo=dt.UTC)
        bob = user_factory(**bob_kwargs)

        if not tx_owner_is_alice:
            carol = user_factory(email="carol@example.com")
            account = account_factory(owner_id=carol.id, name="Carol perso")
            tx_creator = carol.id
        elif personal:
            account = account_factory(owner_id=alice.id, name="Alice perso")
            tx_creator = alice.id
        else:
            account = account_factory(owner_id=None, name="Commun")
            sync_session.add(
                AccountMember(
                    account_id=account.id, user_id=alice.id, default_share_ratio=Decimal("1.0")
                )
            )
            sync_session.flush()
            tx_creator = alice.id

        tx = tx_factory(account_id=account.id, created_by=tx_creator, state=state, splits=False)
        for amount, is_classification in legs:
            category_id = CategoryFactory().id if is_classification else None
            split_factory(
                transaction_id=tx.id,
                account_id=account.id,
                amount_cents=amount,
                currency="EUR",
                category_id=category_id,
            )
        return _Scenario(alice.id, bob.id, account.id, tx.id)

    return await session.run_sync(_do)


def _body(
    requested_from: uuid.UUID, *, ratio: str = "1.0", short_label: str = "Courses"
) -> dict[str, str]:
    return {"requested_from": str(requested_from), "ratio": ratio, "short_label": short_label}


async def _debt_count(session: AsyncSession, *, tx_id: uuid.UUID) -> int:
    stmt = select(func.count()).select_from(Debt).where(Debt.source_transaction_id == tx_id)
    return int((await session.execute(stmt)).scalar_one())


_DEFAULT_LEGS: list[_Leg] = [(-300, False), (300, True)]


# ---------------------------------------------------------------------------
# POST happy path + token derivation
# ---------------------------------------------------------------------------


async def test_post_creates_share_request_201(
    async_client: AsyncClient,
    household_singleton: AsyncSession,
    bound_transaction_factories: TxFactoryBundle,
) -> None:
    s = await _seed(household_singleton, bound_transaction_factories, legs=_DEFAULT_LEGS)

    resp = await async_client.post(
        f"/transactions/{s.tx_id}/share-requests",
        json=_body(s.bob_id),
        headers=_bearer(s.alice_id),
    )

    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["source_transaction_id"] == str(s.tx_id)
    assert body["requested_from"] == str(s.bob_id)
    assert body["short_label"] == "Courses"
    assert "id" in body and "created_at" in body
    # Response never leaks the Debt or the server-only marker.
    assert "materialization_trace" not in body
    assert await _debt_count(household_singleton, tx_id=s.tx_id) == 1


async def test_post_requested_by_is_token_user_not_body(
    async_client: AsyncClient,
    household_singleton: AsyncSession,
    bound_transaction_factories: TxFactoryBundle,
) -> None:
    s = await _seed(household_singleton, bound_transaction_factories, legs=_DEFAULT_LEGS)

    resp = await async_client.post(
        f"/transactions/{s.tx_id}/share-requests",
        json=_body(s.bob_id),
        headers=_bearer(s.alice_id),
    )
    assert resp.status_code == 201, resp.text
    sr_id = uuid.UUID(resp.json()["id"])

    household_singleton.expire_all()
    sr = (
        await household_singleton.execute(select(ShareRequest).where(ShareRequest.id == sr_id))
    ).scalar_one()
    assert sr.requested_by == s.alice_id  # the token's user, never the body


async def test_post_rejects_smuggled_requested_by_422(
    async_client: AsyncClient,
    household_singleton: AsyncSession,
    bound_transaction_factories: TxFactoryBundle,
) -> None:
    s = await _seed(household_singleton, bound_transaction_factories, legs=_DEFAULT_LEGS)
    body = _body(s.bob_id)
    body["requested_by"] = str(s.bob_id)  # smuggled → extra="forbid"

    resp = await async_client.post(
        f"/transactions/{s.tx_id}/share-requests", json=body, headers=_bearer(s.alice_id)
    )
    assert resp.status_code == 422, resp.text


# ---------------------------------------------------------------------------
# Auth guard on BOTH routers
# ---------------------------------------------------------------------------


async def test_post_without_token_401(
    async_client: AsyncClient,
    household_singleton: AsyncSession,
    bound_transaction_factories: TxFactoryBundle,
) -> None:
    s = await _seed(household_singleton, bound_transaction_factories, legs=_DEFAULT_LEGS)
    resp = await async_client.post(f"/transactions/{s.tx_id}/share-requests", json=_body(s.bob_id))
    assert resp.status_code == 401


async def test_delete_without_token_401(async_client: AsyncClient) -> None:
    resp = await async_client.delete(f"/share-requests/{uuid.uuid4()}")
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# 404 (anti-oracle)
# ---------------------------------------------------------------------------


async def test_post_unknown_transaction_404(
    async_client: AsyncClient,
    household_singleton: AsyncSession,
    bound_transaction_factories: TxFactoryBundle,
) -> None:
    s = await _seed(household_singleton, bound_transaction_factories, legs=_DEFAULT_LEGS)
    resp = await async_client.post(
        f"/transactions/{uuid.uuid4()}/share-requests",
        json=_body(s.bob_id),
        headers=_bearer(s.alice_id),
    )
    assert resp.status_code == 404


async def test_post_inaccessible_transaction_404(
    async_client: AsyncClient,
    household_singleton: AsyncSession,
    bound_transaction_factories: TxFactoryBundle,
) -> None:
    s = await _seed(
        household_singleton,
        bound_transaction_factories,
        legs=_DEFAULT_LEGS,
        tx_owner_is_alice=False,
    )
    resp = await async_client.post(
        f"/transactions/{s.tx_id}/share-requests",
        json=_body(s.bob_id),
        headers=_bearer(s.alice_id),
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 422 — one per mapping
# ---------------------------------------------------------------------------


async def test_post_shared_account_422(
    async_client: AsyncClient,
    household_singleton: AsyncSession,
    bound_transaction_factories: TxFactoryBundle,
) -> None:
    s = await _seed(
        household_singleton, bound_transaction_factories, legs=_DEFAULT_LEGS, personal=False
    )
    resp = await async_client.post(
        f"/transactions/{s.tx_id}/share-requests",
        json=_body(s.bob_id),
        headers=_bearer(s.alice_id),
    )
    assert resp.status_code == 422


async def test_post_non_confirmed_422(
    async_client: AsyncClient,
    household_singleton: AsyncSession,
    bound_transaction_factories: TxFactoryBundle,
) -> None:
    s = await _seed(
        household_singleton, bound_transaction_factories, legs=_DEFAULT_LEGS, state="draft"
    )
    resp = await async_client.post(
        f"/transactions/{s.tx_id}/share-requests",
        json=_body(s.bob_id),
        headers=_bearer(s.alice_id),
    )
    assert resp.status_code == 422


async def test_post_requested_from_not_member_422(
    async_client: AsyncClient,
    household_singleton: AsyncSession,
    bound_transaction_factories: TxFactoryBundle,
) -> None:
    s = await _seed(household_singleton, bound_transaction_factories, legs=_DEFAULT_LEGS)
    resp = await async_client.post(
        f"/transactions/{s.tx_id}/share-requests",
        json=_body(uuid.uuid4()),  # unknown user
        headers=_bearer(s.alice_id),
    )
    assert resp.status_code == 422


async def test_post_self_share_422(
    async_client: AsyncClient,
    household_singleton: AsyncSession,
    bound_transaction_factories: TxFactoryBundle,
) -> None:
    s = await _seed(household_singleton, bound_transaction_factories, legs=_DEFAULT_LEGS)
    resp = await async_client.post(
        f"/transactions/{s.tx_id}/share-requests",
        json=_body(s.alice_id),  # requested_from == token user
        headers=_bearer(s.alice_id),
    )
    assert resp.status_code == 422


async def test_post_ratio_out_of_bounds_422(
    async_client: AsyncClient,
    household_singleton: AsyncSession,
    bound_transaction_factories: TxFactoryBundle,
) -> None:
    s = await _seed(household_singleton, bound_transaction_factories, legs=_DEFAULT_LEGS)
    for ratio in ("1.5", "0"):
        resp = await async_client.post(
            f"/transactions/{s.tx_id}/share-requests",
            json=_body(s.bob_id, ratio=ratio),
            headers=_bearer(s.alice_id),
        )
        assert resp.status_code == 422, ratio


async def test_post_bad_short_label_422(
    async_client: AsyncClient,
    household_singleton: AsyncSession,
    bound_transaction_factories: TxFactoryBundle,
) -> None:
    s = await _seed(household_singleton, bound_transaction_factories, legs=_DEFAULT_LEGS)
    bad_labels = [
        "x" * 101,  # too long
        "with\nnewline",  # control
        "with\x00null",  # NUL
        "nbsp" + chr(0x00A0) + "here",  # NBSP (Zs)
        chr(0x0430) + chr(0x0431) + chr(0x0432),  # Cyrillic homoglyphs
        "   ",  # blank after trim
    ]
    for label in bad_labels:
        resp = await async_client.post(
            f"/transactions/{s.tx_id}/share-requests",
            json=_body(s.bob_id, short_label=label),
            headers=_bearer(s.alice_id),
        )
        assert resp.status_code == 422, repr(label)


async def test_post_transfer_no_expense_422(
    async_client: AsyncClient,
    household_singleton: AsyncSession,
    bound_transaction_factories: TxFactoryBundle,
) -> None:
    s = await _seed(
        household_singleton, bound_transaction_factories, legs=[(-300, False), (300, False)]
    )
    resp = await async_client.post(
        f"/transactions/{s.tx_id}/share-requests",
        json=_body(s.bob_id),
        headers=_bearer(s.alice_id),
    )
    assert resp.status_code == 422


async def test_post_degenerate_rounding_422(
    async_client: AsyncClient,
    household_singleton: AsyncSession,
    bound_transaction_factories: TxFactoryBundle,
) -> None:
    # review #144 F1: 1¢ × 0.4 → 0 → non_positive_debt_amount → 422 at the boundary.
    s = await _seed(household_singleton, bound_transaction_factories, legs=[(-1, False), (1, True)])
    resp = await async_client.post(
        f"/transactions/{s.tx_id}/share-requests",
        json=_body(s.bob_id, ratio="0.4"),
        headers=_bearer(s.alice_id),
    )
    assert resp.status_code == 422
    assert await _debt_count(household_singleton, tx_id=s.tx_id) == 0


# ---------------------------------------------------------------------------
# 409 + DELETE + IDOR
# ---------------------------------------------------------------------------


async def test_post_duplicate_409(
    async_client: AsyncClient,
    household_singleton: AsyncSession,
    bound_transaction_factories: TxFactoryBundle,
) -> None:
    s = await _seed(household_singleton, bound_transaction_factories, legs=_DEFAULT_LEGS)
    first = await async_client.post(
        f"/transactions/{s.tx_id}/share-requests",
        json=_body(s.bob_id),
        headers=_bearer(s.alice_id),
    )
    assert first.status_code == 201, first.text
    second = await async_client.post(
        f"/transactions/{s.tx_id}/share-requests",
        json=_body(s.bob_id),
        headers=_bearer(s.alice_id),
    )
    assert second.status_code == 409


async def test_delete_revokes_204_idempotent(
    async_client: AsyncClient,
    household_singleton: AsyncSession,
    bound_transaction_factories: TxFactoryBundle,
) -> None:
    s = await _seed(household_singleton, bound_transaction_factories, legs=_DEFAULT_LEGS)
    created = await async_client.post(
        f"/transactions/{s.tx_id}/share-requests",
        json=_body(s.bob_id),
        headers=_bearer(s.alice_id),
    )
    sr_id = created.json()["id"]

    first = await async_client.delete(f"/share-requests/{sr_id}", headers=_bearer(s.alice_id))
    assert first.status_code == 204
    assert await _debt_count(household_singleton, tx_id=s.tx_id) == 0

    # Re-delete is idempotent (still 204).
    second = await async_client.delete(f"/share-requests/{sr_id}", headers=_bearer(s.alice_id))
    assert second.status_code == 204


async def test_delete_by_non_creditor_404_idor(
    async_client: AsyncClient,
    household_singleton: AsyncSession,
    bound_transaction_factories: TxFactoryBundle,
) -> None:
    s = await _seed(household_singleton, bound_transaction_factories, legs=_DEFAULT_LEGS)
    created = await async_client.post(
        f"/transactions/{s.tx_id}/share-requests",
        json=_body(s.bob_id),
        headers=_bearer(s.alice_id),
    )
    sr_id = created.json()["id"]

    # Bob (the debtor) tries to revoke Alice's SR → uniform 404 (anti-oracle).
    resp = await async_client.delete(f"/share-requests/{sr_id}", headers=_bearer(s.bob_id))
    assert resp.status_code == 404
    assert await _debt_count(household_singleton, tx_id=s.tx_id) == 1  # Debt intact
