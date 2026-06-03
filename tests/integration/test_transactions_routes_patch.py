"""Integration tests for `PATCH /transactions/{id}` (S07.5, P07.5.3).

Drives the editable-fields PATCH over httpx: only `{category_id, tags,
description, debt_generation_override}` are accepted; any frozen/unknown field is
a **422** (`extra="forbid"`), not a silent no-op (the AC). The allowed fields are
editable on a `confirmed` transaction too. Membership is checked first
(non-member — admin included — → 404). A re-read from the DB confirms the write.

Transactions are seeded via the bound factories; the PATCH path never calls
`get_household`, so no household-cache bracketing is needed.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from uuid import UUID, uuid4

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from backend.config import get_settings
from backend.modules.auth.domain import UserRole
from backend.modules.auth.service.jwt import issue_access_token
from backend.modules.transactions.models import Transaction as TxModel

_settings = get_settings()

TxFactoryBundle = Callable[[], Awaitable[tuple[type, type, type, type]]]
CategoryFactory = Callable[..., Awaitable[object]]


def _bearer(user_id: UUID) -> dict[str, str]:
    return {"Authorization": f"Bearer {issue_access_token(user_id, settings=_settings)}"}


async def _read_tx(session: AsyncSession, tx_id: UUID) -> TxModel:
    return (await session.execute(select(TxModel).where(TxModel.id == tx_id))).scalar_one()


async def test_patch_allowed_fields_on_draft(
    async_client: AsyncClient,
    household_singleton: AsyncSession,
    bound_transaction_factories: TxFactoryBundle,
    bound_category_factory: CategoryFactory,
) -> None:
    user_factory, account_factory, tx_factory, _ = await bound_transaction_factories()
    category = await bound_category_factory(name="Loisirs")
    cat_id = category.id  # type: ignore[attr-defined]

    def _seed(_s: Session) -> tuple[UUID, UUID]:
        owner = user_factory(email="d1@example.com")
        acc = account_factory(owner_id=owner.id, name="Perso")
        tx = tx_factory(account_id=acc.id, created_by=owner.id, state="draft")
        return owner.id, tx.id

    owner_id, tx_id = await household_singleton.run_sync(_seed)

    body = {
        "category_id": str(cat_id),
        "tags": ["a", "b"],
        "description": "courses",
        "debt_generation_override": "force_no_debt",
    }
    resp = await async_client.patch(f"/transactions/{tx_id}", json=body, headers=_bearer(owner_id))
    assert resp.status_code == 200, resp.text
    payload = resp.json()
    assert payload["category_id"] == str(cat_id)
    assert payload["tags"] == ["a", "b"]
    assert payload["description"] == "courses"
    assert payload["debt_generation_override"] == "force_no_debt"

    row = await _read_tx(household_singleton, tx_id)
    assert row.category_id == cat_id
    assert row.tags == ["a", "b"]
    assert row.debt_generation_override == "force_no_debt"


async def test_patch_allowed_fields_on_confirmed(
    async_client: AsyncClient,
    household_singleton: AsyncSession,
    bound_transaction_factories: TxFactoryBundle,
    bound_category_factory: CategoryFactory,
) -> None:
    # The four allowed fields stay editable once confirmed (EDITABLE_AFTER_CONFIRMED).
    user_factory, account_factory, tx_factory, split_factory = await bound_transaction_factories()
    category = await bound_category_factory(name="Loisirs")
    cat_id = category.id  # type: ignore[attr-defined]

    def _seed(_s: Session) -> tuple[UUID, UUID]:
        owner = user_factory(email="cf1@example.com")
        acc = account_factory(owner_id=owner.id, name="Perso")
        tx = tx_factory(account_id=acc.id, created_by=owner.id, state="confirmed", splits=False)
        split_factory(
            transaction_id=tx.id, account_id=acc.id, amount_cents=-1000, category_id=cat_id
        )
        split_factory(
            transaction_id=tx.id, account_id=acc.id, amount_cents=1000, category_id=cat_id
        )
        return owner.id, tx.id

    owner_id, tx_id = await household_singleton.run_sync(_seed)

    resp = await async_client.patch(
        f"/transactions/{tx_id}",
        json={"description": "ajustée", "debt_generation_override": "force_full_debt"},
        headers=_bearer(owner_id),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["description"] == "ajustée"
    assert resp.json()["debt_generation_override"] == "force_full_debt"

    row = await _read_tx(household_singleton, tx_id)
    assert row.description == "ajustée"
    assert row.debt_generation_override == "force_full_debt"
    assert row.state == "confirmed"  # editing a confirmed tx does not change its state


async def test_patch_frozen_field_422(
    async_client: AsyncClient,
    household_singleton: AsyncSession,
    bound_transaction_factories: TxFactoryBundle,
) -> None:
    # A frozen/unknown field is a 422 at the schema, never a silent no-op (the AC).
    user_factory, account_factory, tx_factory, _ = await bound_transaction_factories()

    def _seed(_s: Session) -> tuple[UUID, UUID]:
        owner = user_factory(email="f1@example.com")
        acc = account_factory(owner_id=owner.id, name="Perso")
        tx = tx_factory(account_id=acc.id, created_by=owner.id, state="draft")
        return owner.id, tx.id

    owner_id, tx_id = await household_singleton.run_sync(_seed)

    for frozen in (
        {"amount_cents": 999},
        {"account_id": str(uuid4())},
        {"date": "2026-02-02"},
        {"payee": "Carrefour"},
        {"state": "void"},
        {"splits": []},
        # 🔒 Anti-circumvention (D5): `leg_role` is not a PATCH field — the
        # post-creation door to desync `leg_role`/`category_id` stays shut.
        {"leg_role": "funding"},
    ):
        resp = await async_client.patch(
            f"/transactions/{tx_id}", json=frozen, headers=_bearer(owner_id)
        )
        assert resp.status_code == 422, (frozen, resp.text)


async def test_patch_bad_debt_override_422(
    async_client: AsyncClient,
    household_singleton: AsyncSession,
    bound_transaction_factories: TxFactoryBundle,
) -> None:
    user_factory, account_factory, tx_factory, _ = await bound_transaction_factories()

    def _seed(_s: Session) -> tuple[UUID, UUID]:
        owner = user_factory(email="f2@example.com")
        acc = account_factory(owner_id=owner.id, name="Perso")
        tx = tx_factory(account_id=acc.id, created_by=owner.id, state="draft")
        return owner.id, tx.id

    owner_id, tx_id = await household_singleton.run_sync(_seed)

    resp = await async_client.patch(
        f"/transactions/{tx_id}",
        json={"debt_generation_override": "force_partial_debt"},
        headers=_bearer(owner_id),
    )
    assert resp.status_code == 422, resp.text


async def test_patch_description_too_long_422(
    async_client: AsyncClient,
    household_singleton: AsyncSession,
    bound_transaction_factories: TxFactoryBundle,
) -> None:
    user_factory, account_factory, tx_factory, _ = await bound_transaction_factories()

    def _seed(_s: Session) -> tuple[UUID, UUID]:
        owner = user_factory(email="f3@example.com")
        acc = account_factory(owner_id=owner.id, name="Perso")
        tx = tx_factory(account_id=acc.id, created_by=owner.id, state="draft")
        return owner.id, tx.id

    owner_id, tx_id = await household_singleton.run_sync(_seed)

    resp = await async_client.patch(
        f"/transactions/{tx_id}", json={"description": "x" * 501}, headers=_bearer(owner_id)
    )
    assert resp.status_code == 422, resp.text


async def test_patch_too_many_tags_422(
    async_client: AsyncClient,
    household_singleton: AsyncSession,
    bound_transaction_factories: TxFactoryBundle,
) -> None:
    # Same anti-DoS bounds as the create route (tags cardinality ≤ 32).
    user_factory, account_factory, tx_factory, _ = await bound_transaction_factories()

    def _seed(_s: Session) -> tuple[UUID, UUID]:
        owner = user_factory(email="f4@example.com")
        acc = account_factory(owner_id=owner.id, name="Perso")
        tx = tx_factory(account_id=acc.id, created_by=owner.id, state="draft")
        return owner.id, tx.id

    owner_id, tx_id = await household_singleton.run_sync(_seed)

    resp = await async_client.patch(
        f"/transactions/{tx_id}",
        json={"tags": [f"t{i}" for i in range(33)]},
        headers=_bearer(owner_id),
    )
    assert resp.status_code == 422, resp.text


async def test_patch_tag_too_long_422(
    async_client: AsyncClient,
    household_singleton: AsyncSession,
    bound_transaction_factories: TxFactoryBundle,
) -> None:
    # Per-item bound on a tag (≤ 64 chars), not only the cardinality.
    user_factory, account_factory, tx_factory, _ = await bound_transaction_factories()

    def _seed(_s: Session) -> tuple[UUID, UUID]:
        owner = user_factory(email="f5@example.com")
        acc = account_factory(owner_id=owner.id, name="Perso")
        tx = tx_factory(account_id=acc.id, created_by=owner.id, state="draft")
        return owner.id, tx.id

    owner_id, tx_id = await household_singleton.run_sync(_seed)

    resp = await async_client.patch(
        f"/transactions/{tx_id}", json={"tags": ["x" * 65]}, headers=_bearer(owner_id)
    )
    assert resp.status_code == 422, resp.text


async def test_patch_empty_body_noop_200(
    async_client: AsyncClient,
    household_singleton: AsyncSession,
    bound_transaction_factories: TxFactoryBundle,
) -> None:
    # `{}` → 200 no-op (exclude_unset), nothing overwritten.
    user_factory, account_factory, tx_factory, _ = await bound_transaction_factories()

    def _seed(_s: Session) -> tuple[UUID, UUID]:
        owner = user_factory(email="e1@example.com")
        acc = account_factory(owner_id=owner.id, name="Perso")
        tx = tx_factory(
            account_id=acc.id, created_by=owner.id, state="draft", description="initial"
        )
        return owner.id, tx.id

    owner_id, tx_id = await household_singleton.run_sync(_seed)

    resp = await async_client.patch(f"/transactions/{tx_id}", json={}, headers=_bearer(owner_id))
    assert resp.status_code == 200, resp.text
    assert resp.json()["description"] == "initial"


async def test_patch_clears_fields(
    async_client: AsyncClient,
    household_singleton: AsyncSession,
    bound_transaction_factories: TxFactoryBundle,
    bound_category_factory: CategoryFactory,
) -> None:
    # Explicit None / [] are written (distinct from absence).
    user_factory, account_factory, tx_factory, _ = await bound_transaction_factories()
    category = await bound_category_factory(name="X")
    cat_id = category.id  # type: ignore[attr-defined]

    def _seed(_s: Session) -> tuple[UUID, UUID]:
        owner = user_factory(email="e2@example.com")
        acc = account_factory(owner_id=owner.id, name="Perso")
        tx = tx_factory(
            account_id=acc.id,
            created_by=owner.id,
            state="draft",
            description="x",
            category_id=cat_id,
            tags=["keep"],
        )
        return owner.id, tx.id

    owner_id, tx_id = await household_singleton.run_sync(_seed)

    resp = await async_client.patch(
        f"/transactions/{tx_id}",
        json={"category_id": None, "description": None, "tags": []},
        headers=_bearer(owner_id),
    )
    assert resp.status_code == 200, resp.text
    payload = resp.json()
    assert payload["category_id"] is None
    assert payload["description"] is None
    assert payload["tags"] == []

    row = await _read_tx(household_singleton, tx_id)
    assert row.category_id is None
    assert row.description is None
    assert row.tags == []


async def test_patch_non_member_404(
    async_client: AsyncClient,
    household_singleton: AsyncSession,
    bound_transaction_factories: TxFactoryBundle,
) -> None:
    user_factory, account_factory, tx_factory, _ = await bound_transaction_factories()

    def _seed(_s: Session) -> tuple[UUID, UUID]:
        owner = user_factory(email="nm1@example.com")
        outsider = user_factory(email="no1@example.com")
        acc = account_factory(owner_id=owner.id, name="Perso")
        tx = tx_factory(account_id=acc.id, created_by=owner.id, state="draft")
        return outsider.id, tx.id

    outsider_id, tx_id = await household_singleton.run_sync(_seed)

    resp = await async_client.patch(
        f"/transactions/{tx_id}", json={"description": "x"}, headers=_bearer(outsider_id)
    )
    assert resp.status_code == 404, resp.text
    assert resp.json()["detail"] == "Transaction not found."


async def test_patch_admin_not_exempt_404(
    async_client: AsyncClient,
    household_singleton: AsyncSession,
    bound_transaction_factories: TxFactoryBundle,
) -> None:
    user_factory, account_factory, tx_factory, _ = await bound_transaction_factories()

    def _seed(_s: Session) -> tuple[UUID, UUID]:
        admin = user_factory(email="adm2@example.com", role=UserRole.ADMIN)
        member = user_factory(email="mem2@example.com")
        acc = account_factory(owner_id=member.id, name="Perso")
        tx = tx_factory(account_id=acc.id, created_by=member.id, state="draft")
        return admin.id, tx.id

    admin_id, tx_id = await household_singleton.run_sync(_seed)

    resp = await async_client.patch(
        f"/transactions/{tx_id}", json={"description": "x"}, headers=_bearer(admin_id)
    )
    assert resp.status_code == 404, resp.text


async def test_patch_unknown_tx_404(
    async_client: AsyncClient,
    household_singleton: AsyncSession,
    bound_transaction_factories: TxFactoryBundle,
) -> None:
    user_factory, _, _, _ = await bound_transaction_factories()

    def _seed(_s: Session) -> UUID:
        return user_factory(email="ghostp@example.com").id

    user_id = await household_singleton.run_sync(_seed)

    resp = await async_client.patch(
        f"/transactions/{uuid4()}", json={"description": "x"}, headers=_bearer(user_id)
    )
    assert resp.status_code == 404, resp.text


async def test_patch_401_anonymous(
    async_client: AsyncClient,
    household_singleton: AsyncSession,
) -> None:
    resp = await async_client.patch(f"/transactions/{uuid4()}", json={"description": "x"})
    assert resp.status_code == 401
