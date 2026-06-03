"""Integration tests for the transition routes (S07.5, P07.5.2).

`POST /transactions/{id}/confirm|plan|void` over httpx: membership of the
transaction's account is checked BEFORE mutating (non-member — admin included —
→ 404, D4); the state-machine + zero-sum + categorisation gates map to curated
4xx (409 illegal transition, 422 gate failure) and **never** a 500. A tx-id that
does not exist is the same uniform 404 as an inaccessible one.

Transactions/splits are seeded via the bound factories (the routes under test
are the transition path; the rows are set up out-of-band). The routes never call
`get_household`, so no household-cache bracketing is needed.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from uuid import UUID, uuid4

from httpx import AsyncClient
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


async def test_plan_draft_balanced_200(
    async_client: AsyncClient,
    household_singleton: AsyncSession,
    bound_transaction_factories: TxFactoryBundle,
) -> None:
    user_factory, account_factory, tx_factory, _ = await bound_transaction_factories()

    def _seed(_s: Session) -> tuple[UUID, UUID]:
        owner = user_factory(email="p1@example.com")
        acc = account_factory(owner_id=owner.id, name="Perso")
        tx = tx_factory(account_id=acc.id, created_by=owner.id, state="draft")
        return owner.id, tx.id

    owner_id, tx_id = await household_singleton.run_sync(_seed)

    resp = await async_client.post(f"/transactions/{tx_id}/plan", headers=_bearer(owner_id))
    assert resp.status_code == 200, resp.text
    assert resp.json()["state"] == "planned"


async def test_plan_draft_unbalanced_422(
    async_client: AsyncClient,
    household_singleton: AsyncSession,
    bound_transaction_factories: TxFactoryBundle,
) -> None:
    user_factory, account_factory, tx_factory, split_factory = await bound_transaction_factories()

    def _seed(_s: Session) -> tuple[UUID, UUID]:
        owner = user_factory(email="p2@example.com")
        acc = account_factory(owner_id=owner.id, name="Perso")
        tx = tx_factory(account_id=acc.id, created_by=owner.id, state="draft", splits=False)
        split_factory(transaction_id=tx.id, account_id=acc.id, amount_cents=1000)
        split_factory(transaction_id=tx.id, account_id=acc.id, amount_cents=500)
        return owner.id, tx.id

    owner_id, tx_id = await household_singleton.run_sync(_seed)

    resp = await async_client.post(f"/transactions/{tx_id}/plan", headers=_bearer(owner_id))
    assert resp.status_code == 422, resp.text
    assert resp.json()["detail"] == "Transaction splits must sum to zero."


async def test_confirm_planned_categorised_200(
    async_client: AsyncClient,
    household_singleton: AsyncSession,
    bound_transaction_factories: TxFactoryBundle,
    bound_category_factory: CategoryFactory,
) -> None:
    # Canonical form B (ADR 0017): a same-account expense with a `funding` leg
    # (category NULL, -1000) + a `classification` leg (category, +1000). The
    # funding leg is no longer refused → the consuming form confirms via the
    # real flow. This is the core deliverable of S08.5.2.
    user_factory, account_factory, tx_factory, split_factory = await bound_transaction_factories()
    category = await bound_category_factory(name="Courses")
    cat_id = category.id  # type: ignore[attr-defined]

    def _seed(_s: Session) -> tuple[UUID, UUID]:
        owner = user_factory(email="c1@example.com")
        acc = account_factory(owner_id=owner.id, name="Perso")
        tx = tx_factory(account_id=acc.id, created_by=owner.id, state="planned", splits=False)
        split_factory(transaction_id=tx.id, account_id=acc.id, amount_cents=-1000)  # funding (NULL)
        split_factory(
            transaction_id=tx.id, account_id=acc.id, amount_cents=1000, category_id=cat_id
        )  # classification
        return owner.id, tx.id

    owner_id, tx_id = await household_singleton.run_sync(_seed)

    resp = await async_client.post(f"/transactions/{tx_id}/confirm", headers=_bearer(owner_id))
    assert resp.status_code == 200, resp.text
    assert resp.json()["state"] == "confirmed"


async def test_confirm_uncategorised_expense_422(
    async_client: AsyncClient,
    household_singleton: AsyncSession,
    bound_transaction_factories: TxFactoryBundle,
) -> None:
    # ADR 0017: a `classification` leg with a NULL category is still refused. The
    # funding leg (NULL, derived) is exempt; the classification leg's role is
    # FORCED so the divergent/NULL value is what's rejected (not re-derived).
    user_factory, account_factory, tx_factory, split_factory = await bound_transaction_factories()

    def _seed(_s: Session) -> tuple[UUID, UUID]:
        owner = user_factory(email="c2@example.com")
        acc = account_factory(owner_id=owner.id, name="Perso")
        tx = tx_factory(account_id=acc.id, created_by=owner.id, state="planned", splits=False)
        split_factory(transaction_id=tx.id, account_id=acc.id, amount_cents=-1000)  # funding (NULL)
        split_factory(
            transaction_id=tx.id,
            account_id=acc.id,
            amount_cents=1000,
            leg_role="classification",  # forced classification leg with NULL category
        )
        return owner.id, tx.id

    owner_id, tx_id = await household_singleton.run_sync(_seed)

    resp = await async_client.post(f"/transactions/{tx_id}/confirm", headers=_bearer(owner_id))
    assert resp.status_code == 422, resp.text
    assert resp.json()["detail"] == "Every expense split must have a category."


async def test_confirm_two_funding_legs_422(
    async_client: AsyncClient,
    household_singleton: AsyncSession,
    bound_transaction_factories: TxFactoryBundle,
) -> None:
    # D2/D3 (ADR 0017): two NULL-category legs on one account → two `funding`
    # legs → the ≤1-funding invariant trips (categorisation passes, 0
    # classification). Pins the HTTP 422 mapping of the invariant via the real flow.
    user_factory, account_factory, tx_factory, split_factory = await bound_transaction_factories()

    def _seed(_s: Session) -> tuple[UUID, UUID]:
        owner = user_factory(email="c5@example.com")
        acc = account_factory(owner_id=owner.id, name="Perso")
        tx = tx_factory(account_id=acc.id, created_by=owner.id, state="planned", splits=False)
        split_factory(transaction_id=tx.id, account_id=acc.id, amount_cents=-1000)
        split_factory(transaction_id=tx.id, account_id=acc.id, amount_cents=1000)
        return owner.id, tx.id

    owner_id, tx_id = await household_singleton.run_sync(_seed)

    resp = await async_client.post(f"/transactions/{tx_id}/confirm", headers=_bearer(owner_id))
    assert resp.status_code == 422, resp.text
    assert resp.json()["detail"] == "An expense may have at most one funding leg."


async def test_confirm_from_draft_is_409(
    async_client: AsyncClient,
    household_singleton: AsyncSession,
    bound_transaction_factories: TxFactoryBundle,
    bound_category_factory: CategoryFactory,
) -> None:
    # draft → confirmed is not a legal transition (must go through planned).
    user_factory, account_factory, tx_factory, split_factory = await bound_transaction_factories()
    category = await bound_category_factory(name="Courses")
    cat_id = category.id  # type: ignore[attr-defined]

    def _seed(_s: Session) -> tuple[UUID, UUID]:
        owner = user_factory(email="c3@example.com")
        acc = account_factory(owner_id=owner.id, name="Perso")
        tx = tx_factory(account_id=acc.id, created_by=owner.id, state="draft", splits=False)
        split_factory(
            transaction_id=tx.id, account_id=acc.id, amount_cents=-1000, category_id=cat_id
        )
        split_factory(
            transaction_id=tx.id, account_id=acc.id, amount_cents=1000, category_id=cat_id
        )
        return owner.id, tx.id

    owner_id, tx_id = await household_singleton.run_sync(_seed)

    resp = await async_client.post(f"/transactions/{tx_id}/confirm", headers=_bearer(owner_id))
    assert resp.status_code == 409, resp.text
    assert resp.json()["detail"] == "Transaction state does not allow this transition."


async def test_confirm_mixed_currency_422(
    async_client: AsyncClient,
    household_singleton: AsyncSession,
    bound_transaction_factories: TxFactoryBundle,
    bound_category_factory: CategoryFactory,
) -> None:
    user_factory, account_factory, tx_factory, split_factory = await bound_transaction_factories()
    category = await bound_category_factory(name="Courses")
    cat_id = category.id  # type: ignore[attr-defined]

    def _seed(_s: Session) -> tuple[UUID, UUID]:
        owner = user_factory(email="c4@example.com")
        acc = account_factory(owner_id=owner.id, name="Perso")
        tx = tx_factory(account_id=acc.id, created_by=owner.id, state="planned", splits=False)
        split_factory(
            transaction_id=tx.id,
            account_id=acc.id,
            amount_cents=-1000,
            currency="EUR",
            category_id=cat_id,
        )
        split_factory(
            transaction_id=tx.id,
            account_id=acc.id,
            amount_cents=1000,
            currency="USD",
            category_id=cat_id,
        )
        return owner.id, tx.id

    owner_id, tx_id = await household_singleton.run_sync(_seed)

    resp = await async_client.post(f"/transactions/{tx_id}/confirm", headers=_bearer(owner_id))
    assert resp.status_code == 422, resp.text
    assert resp.json()["detail"] == "All splits must share one currency."


async def test_plan_confirmed_is_409(
    async_client: AsyncClient,
    household_singleton: AsyncSession,
    bound_transaction_factories: TxFactoryBundle,
    bound_category_factory: CategoryFactory,
) -> None:
    # confirmed → planned is forbidden (ADR 0001): reopening frozen amounts.
    user_factory, account_factory, tx_factory, split_factory = await bound_transaction_factories()
    category = await bound_category_factory(name="Courses")
    cat_id = category.id  # type: ignore[attr-defined]

    def _seed(_s: Session) -> tuple[UUID, UUID]:
        owner = user_factory(email="p3@example.com")
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

    resp = await async_client.post(f"/transactions/{tx_id}/plan", headers=_bearer(owner_id))
    assert resp.status_code == 409, resp.text


async def test_void_succeeds_from_draft(
    async_client: AsyncClient,
    household_singleton: AsyncSession,
    bound_transaction_factories: TxFactoryBundle,
) -> None:
    user_factory, account_factory, tx_factory, _ = await bound_transaction_factories()

    def _seed(_s: Session) -> tuple[UUID, UUID]:
        owner = user_factory(email="v1@example.com")
        acc = account_factory(owner_id=owner.id, name="Perso")
        tx = tx_factory(account_id=acc.id, created_by=owner.id, state="draft")
        return owner.id, tx.id

    owner_id, tx_id = await household_singleton.run_sync(_seed)

    resp = await async_client.post(
        f"/transactions/{tx_id}/void",
        json={"reason": "erreur de saisie"},
        headers=_bearer(owner_id),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["state"] == "void"


async def test_void_no_body_succeeds(
    async_client: AsyncClient,
    household_singleton: AsyncSession,
    bound_transaction_factories: TxFactoryBundle,
) -> None:
    user_factory, account_factory, tx_factory, _ = await bound_transaction_factories()

    def _seed(_s: Session) -> tuple[UUID, UUID]:
        owner = user_factory(email="v2@example.com")
        acc = account_factory(owner_id=owner.id, name="Perso")
        tx = tx_factory(account_id=acc.id, created_by=owner.id, state="draft")
        return owner.id, tx.id

    owner_id, tx_id = await household_singleton.run_sync(_seed)

    resp = await async_client.post(f"/transactions/{tx_id}/void", headers=_bearer(owner_id))
    assert resp.status_code == 200, resp.text
    assert resp.json()["state"] == "void"


async def test_void_succeeds_from_planned(
    async_client: AsyncClient,
    household_singleton: AsyncSession,
    bound_transaction_factories: TxFactoryBundle,
) -> None:
    # void is allowed from every non-terminal state (ADR 0001), not just draft.
    user_factory, account_factory, tx_factory, _ = await bound_transaction_factories()

    def _seed(_s: Session) -> tuple[UUID, UUID]:
        owner = user_factory(email="v5@example.com")
        acc = account_factory(owner_id=owner.id, name="Perso")
        tx = tx_factory(account_id=acc.id, created_by=owner.id, state="planned")
        return owner.id, tx.id

    owner_id, tx_id = await household_singleton.run_sync(_seed)

    resp = await async_client.post(f"/transactions/{tx_id}/void", headers=_bearer(owner_id))
    assert resp.status_code == 200, resp.text
    assert resp.json()["state"] == "void"


async def test_void_succeeds_from_confirmed(
    async_client: AsyncClient,
    household_singleton: AsyncSession,
    bound_transaction_factories: TxFactoryBundle,
) -> None:
    # Voiding a confirmed transaction is the reversal path (ADR 0001): allowed.
    user_factory, account_factory, tx_factory, _ = await bound_transaction_factories()

    def _seed(_s: Session) -> tuple[UUID, UUID]:
        owner = user_factory(email="v6@example.com")
        acc = account_factory(owner_id=owner.id, name="Perso")
        tx = tx_factory(account_id=acc.id, created_by=owner.id, state="confirmed")
        return owner.id, tx.id

    owner_id, tx_id = await household_singleton.run_sync(_seed)

    resp = await async_client.post(f"/transactions/{tx_id}/void", headers=_bearer(owner_id))
    assert resp.status_code == 200, resp.text
    assert resp.json()["state"] == "void"


async def test_void_terminal_revoid_409(
    async_client: AsyncClient,
    household_singleton: AsyncSession,
    bound_transaction_factories: TxFactoryBundle,
) -> None:
    user_factory, account_factory, tx_factory, _ = await bound_transaction_factories()

    def _seed(_s: Session) -> tuple[UUID, UUID]:
        owner = user_factory(email="v3@example.com")
        acc = account_factory(owner_id=owner.id, name="Perso")
        tx = tx_factory(account_id=acc.id, created_by=owner.id, state="void")
        return owner.id, tx.id

    owner_id, tx_id = await household_singleton.run_sync(_seed)

    resp = await async_client.post(f"/transactions/{tx_id}/void", headers=_bearer(owner_id))
    assert resp.status_code == 409, resp.text


async def test_void_reason_too_long_422(
    async_client: AsyncClient,
    household_singleton: AsyncSession,
    bound_transaction_factories: TxFactoryBundle,
) -> None:
    user_factory, account_factory, tx_factory, _ = await bound_transaction_factories()

    def _seed(_s: Session) -> tuple[UUID, UUID]:
        owner = user_factory(email="v4@example.com")
        acc = account_factory(owner_id=owner.id, name="Perso")
        tx = tx_factory(account_id=acc.id, created_by=owner.id, state="draft")
        return owner.id, tx.id

    owner_id, tx_id = await household_singleton.run_sync(_seed)

    resp = await async_client.post(
        f"/transactions/{tx_id}/void", json={"reason": "x" * 501}, headers=_bearer(owner_id)
    )
    assert resp.status_code == 422, resp.text


async def test_transition_non_member_404(
    async_client: AsyncClient,
    household_singleton: AsyncSession,
    bound_transaction_factories: TxFactoryBundle,
) -> None:
    user_factory, account_factory, tx_factory, _ = await bound_transaction_factories()

    def _seed(_s: Session) -> tuple[UUID, UUID]:
        owner = user_factory(email="m1@example.com")
        outsider = user_factory(email="out1@example.com")
        acc = account_factory(owner_id=owner.id, name="Perso")
        tx = tx_factory(account_id=acc.id, created_by=owner.id, state="draft")
        return outsider.id, tx.id

    outsider_id, tx_id = await household_singleton.run_sync(_seed)

    for verb in ("confirm", "plan", "void"):
        resp = await async_client.post(
            f"/transactions/{tx_id}/{verb}", headers=_bearer(outsider_id)
        )
        assert resp.status_code == 404, (verb, resp.text)
        assert resp.json()["detail"] == "Transaction not found."


async def test_transition_admin_not_exempt_404(
    async_client: AsyncClient,
    household_singleton: AsyncSession,
    bound_transaction_factories: TxFactoryBundle,
) -> None:
    user_factory, account_factory, tx_factory, _ = await bound_transaction_factories()

    def _seed(_s: Session) -> tuple[UUID, UUID]:
        admin = user_factory(email="adm1@example.com", role=UserRole.ADMIN)
        member = user_factory(email="mem1@example.com")
        acc = account_factory(owner_id=member.id, name="Perso")
        tx = tx_factory(account_id=acc.id, created_by=member.id, state="draft")
        return admin.id, tx.id

    admin_id, tx_id = await household_singleton.run_sync(_seed)

    resp = await async_client.post(f"/transactions/{tx_id}/confirm", headers=_bearer(admin_id))
    assert resp.status_code == 404, resp.text


async def test_transition_unknown_tx_404(
    async_client: AsyncClient,
    household_singleton: AsyncSession,
    bound_transaction_factories: TxFactoryBundle,
) -> None:
    user_factory, _, _, _ = await bound_transaction_factories()

    def _seed(_s: Session) -> UUID:
        return user_factory(email="ghost@example.com").id

    user_id = await household_singleton.run_sync(_seed)

    resp = await async_client.post(f"/transactions/{uuid4()}/confirm", headers=_bearer(user_id))
    assert resp.status_code == 404, resp.text


async def test_transition_401_anonymous(
    async_client: AsyncClient,
    household_singleton: AsyncSession,
) -> None:
    # Each verb is guarded by `Depends(get_current_user)` → 401 without a bearer.
    for verb in ("confirm", "plan", "void"):
        resp = await async_client.post(f"/transactions/{uuid4()}/{verb}")
        assert resp.status_code == 401, (verb, resp.text)
