"""Integration tests for `POST /accounts/{id}/transactions` (S07.5, P07.5.1).

Drives transaction creation over httpx: a member of `{id}` creates a `draft` +
its splits + editable metadata; `created_by` is the token's user (never the
body, D6); a non-member — admin included — gets a uniform **404** (F03/D4). Each
split `account_id` is household-validated at the boundary (D5): an inaccessible
one is a 422 with a generic detail (no id echo). Anti-DoS bounds and
`extra="forbid"` reject malformed bodies at the schema edge.

Accounts/users are seeded via the bound factories (the route under test is the
write path; the FK target rows are set up out-of-band). The create path never
calls `get_household`, so no household-cache bracketing is needed.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from uuid import UUID, uuid4

from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from backend.config import get_settings
from backend.modules.auth.domain import UserRole
from backend.modules.auth.service.jwt import issue_access_token

_settings = get_settings()

TxFactoryBundle = Callable[[], Awaitable[tuple[type, type, type, type]]]
CategoryFactory = Callable[..., Awaitable[object]]


def _bearer(user_id: UUID) -> dict[str, str]:
    return {"Authorization": f"Bearer {issue_access_token(user_id, settings=_settings)}"}


def _split(
    account_id: UUID, amount_cents: int, *, category_id: UUID | None = None
) -> dict[str, object]:
    body: dict[str, object] = {
        "account_id": str(account_id),
        "amount_cents": amount_cents,
        "currency": "EUR",
    }
    if category_id is not None:
        body["category_id"] = str(category_id)
    return body


async def test_create_nominal(
    async_client: AsyncClient,
    household_singleton: AsyncSession,
    bound_transaction_factories: TxFactoryBundle,
    bound_category_factory: CategoryFactory,
) -> None:
    user_factory, account_factory, _, _ = await bound_transaction_factories()
    category = await bound_category_factory(name="Courses")

    def _seed(_s: Session) -> tuple[UUID, UUID]:
        owner = user_factory(email="owner@example.com")
        acc = account_factory(owner_id=owner.id, name="Perso")
        return owner.id, acc.id

    owner_id, acc_id = await household_singleton.run_sync(_seed)
    cat_id = category.id  # type: ignore[attr-defined]

    payload = {
        "date": "2026-01-15",
        "splits": [
            _split(acc_id, -1000, category_id=cat_id),
            _split(acc_id, 1000, category_id=cat_id),
        ],
        "category_id": str(cat_id),
        "description": "Courses du samedi",
        "tags": ["alim"],
        "debt_generation_override": "force_full_debt",
    }
    resp = await async_client.post(
        f"/accounts/{acc_id}/transactions", json=payload, headers=_bearer(owner_id)
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["state"] == "draft"
    assert body["created_by"] == str(owner_id)
    assert body["account_id"] == str(acc_id)
    assert body["category_id"] == str(cat_id)
    assert body["description"] == "Courses du samedi"
    assert body["tags"] == ["alim"]
    assert body["debt_generation_override"] == "force_full_debt"
    assert len(body["splits"]) == 2
    assert {s["amount_cents"] for s in body["splits"]} == {-1000, 1000}


async def test_create_rejects_leg_role_in_split_payload(
    async_client: AsyncClient,
    household_singleton: AsyncSession,
    bound_transaction_factories: TxFactoryBundle,
) -> None:
    # 🔒 Anti-circumvention (D5): `leg_role` is NOT a field of `SplitInput` nor of
    # `TransactionCreate` (both `extra="forbid"`). A client trying to mark a real
    # expense leg `funding` (to escape mandatory categorisation) gets a 422 — not
    # a silent drop — whether it slips `leg_role` into a split OR at the root.
    user_factory, account_factory, _, _ = await bound_transaction_factories()

    def _seed(_s: Session) -> tuple[UUID, UUID]:
        owner = user_factory(email="legrole1@example.com")
        acc = account_factory(owner_id=owner.id, name="Perso")
        return owner.id, acc.id

    owner_id, acc_id = await household_singleton.run_sync(_seed)

    split = {**_split(acc_id, -1000), "leg_role": "funding"}
    payloads = (
        {"splits": [split, _split(acc_id, 1000)]},  # leg_role inside a split
        {"splits": [_split(acc_id, -1000), _split(acc_id, 1000)], "leg_role": "funding"},  # root
    )
    for payload in payloads:
        resp = await async_client.post(
            f"/accounts/{acc_id}/transactions", json=payload, headers=_bearer(owner_id)
        )
        assert resp.status_code == 422, resp.text


async def test_created_split_leg_role_is_server_derived(
    async_client: AsyncClient,
    household_singleton: AsyncSession,
    bound_transaction_factories: TxFactoryBundle,
    bound_category_factory: CategoryFactory,
) -> None:
    # D5: the server derives `leg_role` from `category_id` — never from the
    # payload (the field does not exist there). A categorised leg becomes
    # `classification`; a NULL one becomes `funding`. Read straight from the DB.
    user_factory, account_factory, _, _ = await bound_transaction_factories()
    category = await bound_category_factory(name="Courses")
    cat_id = category.id  # type: ignore[attr-defined]

    def _seed(_s: Session) -> tuple[UUID, UUID]:
        owner = user_factory(email="legrole2@example.com")
        acc = account_factory(owner_id=owner.id, name="Perso")
        return owner.id, acc.id

    owner_id, acc_id = await household_singleton.run_sync(_seed)

    payload = {
        "splits": [
            _split(acc_id, -1000),  # NULL category -> funding
            _split(acc_id, 1000, category_id=cat_id),  # category -> classification
        ]
    }
    resp = await async_client.post(
        f"/accounts/{acc_id}/transactions", json=payload, headers=_bearer(owner_id)
    )
    assert resp.status_code == 201, resp.text
    tx_id = resp.json()["id"]

    rows = (
        await household_singleton.execute(
            text(
                "SELECT category_id, leg_role FROM splits "
                "WHERE transaction_id = :id ORDER BY amount_cents"
            ),
            {"id": tx_id},
        )
    ).all()
    funding, classification = rows
    assert funding.category_id is None
    assert funding.leg_role == "funding"
    assert classification.category_id == cat_id
    assert classification.leg_role == "classification"


async def test_create_created_by_not_injectable(
    async_client: AsyncClient,
    household_singleton: AsyncSession,
    bound_transaction_factories: TxFactoryBundle,
) -> None:
    # D6: a `created_by` slipped into the body is rejected (extra="forbid"), not
    # silently dropped — the invariant "created_by comes from the token" holds
    # even more strongly.
    user_factory, account_factory, _, _ = await bound_transaction_factories()

    def _seed(_s: Session) -> tuple[UUID, UUID]:
        owner = user_factory(email="owner2@example.com")
        acc = account_factory(owner_id=owner.id, name="Perso")
        return owner.id, acc.id

    owner_id, acc_id = await household_singleton.run_sync(_seed)

    payload = {
        "splits": [_split(acc_id, -1000), _split(acc_id, 1000)],
        "created_by": str(uuid4()),
    }
    resp = await async_client.post(
        f"/accounts/{acc_id}/transactions", json=payload, headers=_bearer(owner_id)
    )
    assert resp.status_code == 422, resp.text


async def test_create_non_member_404(
    async_client: AsyncClient,
    household_singleton: AsyncSession,
    bound_transaction_factories: TxFactoryBundle,
) -> None:
    user_factory, account_factory, _, _ = await bound_transaction_factories()

    def _seed(_s: Session) -> tuple[UUID, UUID]:
        owner = user_factory(email="owner3@example.com")
        outsider = user_factory(email="out3@example.com")
        acc = account_factory(owner_id=owner.id, name="Perso")
        return outsider.id, acc.id

    outsider_id, acc_id = await household_singleton.run_sync(_seed)

    payload = {"splits": [_split(acc_id, -1000), _split(acc_id, 1000)]}
    resp = await async_client.post(
        f"/accounts/{acc_id}/transactions", json=payload, headers=_bearer(outsider_id)
    )
    assert resp.status_code == 404, resp.text
    assert resp.json()["detail"] == "Transaction not found."


async def test_create_admin_not_exempt_404(
    async_client: AsyncClient,
    household_singleton: AsyncSession,
    bound_transaction_factories: TxFactoryBundle,
) -> None:
    # F03/D3: an admin who is not a member of the account gets the same 404.
    user_factory, account_factory, _, _ = await bound_transaction_factories()

    def _seed(_s: Session) -> tuple[UUID, UUID]:
        admin = user_factory(email="admin@example.com", role=UserRole.ADMIN)
        member = user_factory(email="member@example.com")
        acc = account_factory(owner_id=member.id, name="Member perso")
        return admin.id, acc.id

    admin_id, acc_id = await household_singleton.run_sync(_seed)

    payload = {"splits": [_split(acc_id, -1000), _split(acc_id, 1000)]}
    resp = await async_client.post(
        f"/accounts/{acc_id}/transactions", json=payload, headers=_bearer(admin_id)
    )
    assert resp.status_code == 404, resp.text


async def test_create_inaccessible_split_account_422(
    async_client: AsyncClient,
    household_singleton: AsyncSession,
    bound_transaction_factories: TxFactoryBundle,
) -> None:
    # D5: a split referencing an account the caller cannot reach → 422, generic
    # detail (no id echo). The route account is accessible; the split is not.
    user_factory, account_factory, _, _ = await bound_transaction_factories()

    def _seed(_s: Session) -> tuple[UUID, UUID, UUID]:
        owner = user_factory(email="owner4@example.com")
        stranger = user_factory(email="stranger4@example.com")
        mine = account_factory(owner_id=owner.id, name="Mine")
        foreign = account_factory(owner_id=stranger.id, name="Foreign")
        return owner.id, mine.id, foreign.id

    owner_id, mine_id, foreign_id = await household_singleton.run_sync(_seed)

    payload = {"splits": [_split(mine_id, -1000), _split(foreign_id, 1000)]}
    resp = await async_client.post(
        f"/accounts/{mine_id}/transactions", json=payload, headers=_bearer(owner_id)
    )
    assert resp.status_code == 422, resp.text
    assert resp.json()["detail"] == "A split references an inaccessible account."


async def test_create_legit_transfer_201(
    async_client: AsyncClient,
    household_singleton: AsyncSession,
    bound_transaction_factories: TxFactoryBundle,
) -> None:
    # A genuine transfer: two accounts of the household the user can reach.
    user_factory, account_factory, _, _ = await bound_transaction_factories()

    def _seed(_s: Session) -> tuple[UUID, UUID, UUID]:
        owner = user_factory(email="owner5@example.com")
        a = account_factory(owner_id=owner.id, name="Courant")
        b = account_factory(owner_id=owner.id, name="Epargne")
        return owner.id, a.id, b.id

    owner_id, a_id, b_id = await household_singleton.run_sync(_seed)

    payload = {"splits": [_split(a_id, -1000), _split(b_id, 1000)]}
    resp = await async_client.post(
        f"/accounts/{a_id}/transactions", json=payload, headers=_bearer(owner_id)
    )
    assert resp.status_code == 201, resp.text
    assert {s["account_id"] for s in resp.json()["splits"]} == {str(a_id), str(b_id)}


async def test_create_bad_debt_override_422(
    async_client: AsyncClient,
    household_singleton: AsyncSession,
    bound_transaction_factories: TxFactoryBundle,
) -> None:
    # Out-of-enum `debt_generation_override` → 422 at the schema `Literal`,
    # before the service (the CHECK backstop is unreachable via the body).
    user_factory, account_factory, _, _ = await bound_transaction_factories()

    def _seed(_s: Session) -> tuple[UUID, UUID]:
        owner = user_factory(email="owner6@example.com")
        acc = account_factory(owner_id=owner.id, name="Perso")
        return owner.id, acc.id

    owner_id, acc_id = await household_singleton.run_sync(_seed)

    payload = {
        "splits": [_split(acc_id, -1000), _split(acc_id, 1000)],
        "debt_generation_override": "force_partial_debt",
    }
    resp = await async_client.post(
        f"/accounts/{acc_id}/transactions", json=payload, headers=_bearer(owner_id)
    )
    assert resp.status_code == 422, resp.text


async def test_create_description_too_long_422(
    async_client: AsyncClient,
    household_singleton: AsyncSession,
    bound_transaction_factories: TxFactoryBundle,
) -> None:
    user_factory, account_factory, _, _ = await bound_transaction_factories()

    def _seed(_s: Session) -> tuple[UUID, UUID]:
        owner = user_factory(email="owner7@example.com")
        acc = account_factory(owner_id=owner.id, name="Perso")
        return owner.id, acc.id

    owner_id, acc_id = await household_singleton.run_sync(_seed)

    payload = {
        "splits": [_split(acc_id, -1000), _split(acc_id, 1000)],
        "description": "x" * 501,
    }
    resp = await async_client.post(
        f"/accounts/{acc_id}/transactions", json=payload, headers=_bearer(owner_id)
    )
    assert resp.status_code == 422, resp.text


async def test_create_too_many_tags_422(
    async_client: AsyncClient,
    household_singleton: AsyncSession,
    bound_transaction_factories: TxFactoryBundle,
) -> None:
    user_factory, account_factory, _, _ = await bound_transaction_factories()

    def _seed(_s: Session) -> tuple[UUID, UUID]:
        owner = user_factory(email="owner8@example.com")
        acc = account_factory(owner_id=owner.id, name="Perso")
        return owner.id, acc.id

    owner_id, acc_id = await household_singleton.run_sync(_seed)

    payload = {
        "splits": [_split(acc_id, -1000), _split(acc_id, 1000)],
        "tags": [f"t{i}" for i in range(33)],
    }
    resp = await async_client.post(
        f"/accounts/{acc_id}/transactions", json=payload, headers=_bearer(owner_id)
    )
    assert resp.status_code == 422, resp.text


async def test_create_tag_item_too_long_422(
    async_client: AsyncClient,
    household_singleton: AsyncSession,
    bound_transaction_factories: TxFactoryBundle,
) -> None:
    user_factory, account_factory, _, _ = await bound_transaction_factories()

    def _seed(_s: Session) -> tuple[UUID, UUID]:
        owner = user_factory(email="owner9@example.com")
        acc = account_factory(owner_id=owner.id, name="Perso")
        return owner.id, acc.id

    owner_id, acc_id = await household_singleton.run_sync(_seed)

    payload = {
        "splits": [_split(acc_id, -1000), _split(acc_id, 1000)],
        "tags": ["x" * 65],
    }
    resp = await async_client.post(
        f"/accounts/{acc_id}/transactions", json=payload, headers=_bearer(owner_id)
    )
    assert resp.status_code == 422, resp.text


async def test_create_foreign_field_forbidden_422(
    async_client: AsyncClient,
    household_singleton: AsyncSession,
    bound_transaction_factories: TxFactoryBundle,
) -> None:
    # `extra="forbid"`: a frozen/unknown field (`payee`, `state`, …) → 422.
    user_factory, account_factory, _, _ = await bound_transaction_factories()

    def _seed(_s: Session) -> tuple[UUID, UUID]:
        owner = user_factory(email="owner10@example.com")
        acc = account_factory(owner_id=owner.id, name="Perso")
        return owner.id, acc.id

    owner_id, acc_id = await household_singleton.run_sync(_seed)

    payload = {
        "splits": [_split(acc_id, -1000), _split(acc_id, 1000)],
        "payee": "Carrefour",
    }
    resp = await async_client.post(
        f"/accounts/{acc_id}/transactions", json=payload, headers=_bearer(owner_id)
    )
    assert resp.status_code == 422, resp.text


async def test_create_empty_splits_422(
    async_client: AsyncClient,
    household_singleton: AsyncSession,
    bound_transaction_factories: TxFactoryBundle,
) -> None:
    user_factory, account_factory, _, _ = await bound_transaction_factories()

    def _seed(_s: Session) -> tuple[UUID, UUID]:
        owner = user_factory(email="owner11@example.com")
        acc = account_factory(owner_id=owner.id, name="Perso")
        return owner.id, acc.id

    owner_id, acc_id = await household_singleton.run_sync(_seed)

    resp = await async_client.post(
        f"/accounts/{acc_id}/transactions", json={"splits": []}, headers=_bearer(owner_id)
    )
    assert resp.status_code == 422, resp.text


async def test_create_too_many_splits_422(
    async_client: AsyncClient,
    household_singleton: AsyncSession,
    bound_transaction_factories: TxFactoryBundle,
) -> None:
    user_factory, account_factory, _, _ = await bound_transaction_factories()

    def _seed(_s: Session) -> tuple[UUID, UUID]:
        owner = user_factory(email="owner12@example.com")
        acc = account_factory(owner_id=owner.id, name="Perso")
        return owner.id, acc.id

    owner_id, acc_id = await household_singleton.run_sync(_seed)

    payload = {"splits": [_split(acc_id, 0) for _ in range(101)]}
    resp = await async_client.post(
        f"/accounts/{acc_id}/transactions", json=payload, headers=_bearer(owner_id)
    )
    assert resp.status_code == 422, resp.text


async def test_create_401_anonymous(
    async_client: AsyncClient,
    household_singleton: AsyncSession,
) -> None:
    resp = await async_client.post(f"/accounts/{uuid4()}/transactions", json={"splits": []})
    assert resp.status_code == 401
