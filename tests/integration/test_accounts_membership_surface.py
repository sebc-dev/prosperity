"""Integration tests for the `accounts.public` membership surface (S07.5, P07.5.0).

`account_is_accessible` / `accessible_account_ids` are the primitives the
transactions routes (S07.5) call to enforce F03 watertightness by **membership**
(never `require_admin`). Both reuse `_accessible`, so the load-bearing assertion
is the same as the account routes: the **admin is not exempt** — it neither
passes `account_is_accessible` nor appears in `accessible_account_ids` for an
account it does not own / is not a member of. Archived accounts are invisible.

Exercised directly against the service surface (not over httpx): these are the
building blocks the route layer composes, so we pin their DB behaviour here.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from backend.modules.accounts.public import accessible_account_ids, account_is_accessible
from backend.modules.auth.domain import UserRole

FactoryBundle = Callable[[], Awaitable[tuple[type, type, type]]]


async def test_is_accessible_owner_of_personal(
    household_singleton: AsyncSession,
    bound_account_factories: FactoryBundle,
) -> None:
    user_factory, account_factory, _ = await bound_account_factories()

    def _seed(_s: Session) -> tuple[UUID, UUID]:
        owner = user_factory(email="owner@example.com")
        acc = account_factory(owner_id=owner.id, name="Perso")
        return owner.id, acc.id

    owner_id, acc_id = await household_singleton.run_sync(_seed)

    assert await account_is_accessible(household_singleton, account_id=acc_id, user_id=owner_id)


async def test_is_accessible_non_owner_false(
    household_singleton: AsyncSession,
    bound_account_factories: FactoryBundle,
) -> None:
    user_factory, account_factory, _ = await bound_account_factories()

    def _seed(_s: Session) -> tuple[UUID, UUID]:
        owner = user_factory(email="owner2@example.com")
        other = user_factory(email="other2@example.com")
        acc = account_factory(owner_id=owner.id, name="Perso")
        return other.id, acc.id

    other_id, acc_id = await household_singleton.run_sync(_seed)

    assert not await account_is_accessible(household_singleton, account_id=acc_id, user_id=other_id)


async def test_is_accessible_member_of_shared(
    household_singleton: AsyncSession,
    bound_account_factories: FactoryBundle,
) -> None:
    user_factory, account_factory, member_factory = await bound_account_factories()

    def _seed(_s: Session) -> tuple[UUID, UUID]:
        u1 = user_factory(email="m1@example.com")
        u2 = user_factory(email="m2@example.com")
        shared = account_factory(owner_id=None, name="Commun")
        member_factory(account_id=shared.id, user_id=u1.id)
        member_factory(account_id=shared.id, user_id=u2.id)
        return u1.id, shared.id

    u1_id, shared_id = await household_singleton.run_sync(_seed)

    assert await account_is_accessible(household_singleton, account_id=shared_id, user_id=u1_id)


async def test_is_accessible_non_member_of_shared_false(
    household_singleton: AsyncSession,
    bound_account_factories: FactoryBundle,
) -> None:
    user_factory, account_factory, member_factory = await bound_account_factories()

    def _seed(_s: Session) -> tuple[UUID, UUID]:
        u1 = user_factory(email="in1@example.com")
        u2 = user_factory(email="in2@example.com")
        outsider = user_factory(email="out@example.com")
        shared = account_factory(owner_id=None, name="Commun")
        member_factory(account_id=shared.id, user_id=u1.id)
        member_factory(account_id=shared.id, user_id=u2.id)
        return outsider.id, shared.id

    outsider_id, shared_id = await household_singleton.run_sync(_seed)

    assert not await account_is_accessible(
        household_singleton, account_id=shared_id, user_id=outsider_id
    )


async def test_is_accessible_archived_false(
    household_singleton: AsyncSession,
    bound_account_factories: FactoryBundle,
) -> None:
    user_factory, account_factory, _ = await bound_account_factories()

    def _seed(_s: Session) -> tuple[UUID, UUID]:
        owner = user_factory(email="arch@example.com")
        acc = account_factory(owner_id=owner.id, name="Archived", archived_at=datetime.now(tz=UTC))
        return owner.id, acc.id

    owner_id, acc_id = await household_singleton.run_sync(_seed)

    assert not await account_is_accessible(household_singleton, account_id=acc_id, user_id=owner_id)


async def test_is_accessible_admin_not_exempt(
    household_singleton: AsyncSession,
    bound_account_factories: FactoryBundle,
) -> None:
    # F03 (D3): the admin is not exempt — it cannot access another user's
    # personal account through the membership predicate.
    user_factory, account_factory, _ = await bound_account_factories()

    def _seed(_s: Session) -> tuple[UUID, UUID]:
        admin = user_factory(email="admin@example.com", role=UserRole.ADMIN)
        member = user_factory(email="member@example.com")
        acc = account_factory(owner_id=member.id, name="Member perso")
        return admin.id, acc.id

    admin_id, acc_id = await household_singleton.run_sync(_seed)

    assert not await account_is_accessible(household_singleton, account_id=acc_id, user_id=admin_id)


async def test_is_accessible_unknown_id_false(
    household_singleton: AsyncSession,
    bound_account_factories: FactoryBundle,
) -> None:
    user_factory, _, _ = await bound_account_factories()

    def _seed(_s: Session) -> UUID:
        return user_factory(email="ghost@example.com").id

    user_id = await household_singleton.run_sync(_seed)

    assert not await account_is_accessible(household_singleton, account_id=uuid4(), user_id=user_id)


async def test_accessible_ids_owned_and_shared_excludes_archived(
    household_singleton: AsyncSession,
    bound_account_factories: FactoryBundle,
) -> None:
    user_factory, account_factory, member_factory = await bound_account_factories()

    def _seed(_s: Session) -> tuple[UUID, UUID, UUID]:
        user = user_factory(email="multi@example.com")
        other = user_factory(email="stranger@example.com")
        owned = account_factory(owner_id=user.id, name="Owned")
        shared = account_factory(owner_id=None, name="Shared")
        member_factory(account_id=shared.id, user_id=user.id)
        member_factory(account_id=shared.id, user_id=other.id)
        # Excluded: archived (owned) + a stranger's personal account.
        account_factory(owner_id=user.id, name="Archived", archived_at=datetime.now(tz=UTC))
        account_factory(owner_id=other.id, name="Stranger perso")
        return user.id, owned.id, shared.id

    user_id, owned_id, shared_id = await household_singleton.run_sync(_seed)

    assert await accessible_account_ids(household_singleton, user_id=user_id) == {
        owned_id,
        shared_id,
    }


async def test_accessible_ids_admin_not_exempt(
    household_singleton: AsyncSession,
    bound_account_factories: FactoryBundle,
) -> None:
    user_factory, account_factory, _ = await bound_account_factories()

    def _seed(_s: Session) -> UUID:
        admin = user_factory(email="admin2@example.com", role=UserRole.ADMIN)
        member = user_factory(email="member2@example.com")
        account_factory(owner_id=member.id, name="Member perso")
        return admin.id

    admin_id = await household_singleton.run_sync(_seed)

    assert await accessible_account_ids(household_singleton, user_id=admin_id) == set()


async def test_accessible_ids_empty_for_new_user(
    household_singleton: AsyncSession,
    bound_account_factories: FactoryBundle,
) -> None:
    user_factory, _, _ = await bound_account_factories()

    def _seed(_s: Session) -> UUID:
        return user_factory(email="newbie@example.com").id

    user_id = await household_singleton.run_sync(_seed)

    assert await accessible_account_ids(household_singleton, user_id=user_id) == set()
