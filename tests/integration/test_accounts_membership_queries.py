"""Integration tests for the S08.2 membership helpers (`accounts.service.accounts`).

`owned_personal_account_ids` / `shared_account_ids_with_members_subset` are the
two id-only primitives the budget-consumption service consumes through
`accounts.public` to bound which splits a budget counts (D7). They are read-only
and selected against a real Postgres so the `owner_id IS NULL/NOT NULL`
ownership shape, the archived-exclusion, and the **subset** semantics
(members ⊆ member_ids, not equality) actually fire.

Gabarit `test_accounts_membership_surface.py` (same `bound_account_factories`
seed-in-`run_sync` pattern).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from backend.modules.accounts.public import (
    owned_personal_account_ids,
    shared_account_ids_with_members_subset,
)

FactoryBundle = Callable[[], Awaitable[tuple[type, type, type]]]


# ---------------------------------------------------------------------------
# owned_personal_account_ids
# ---------------------------------------------------------------------------


async def test_owned_personal_account_ids_returns_only_owned_personal(
    household_singleton: AsyncSession,
    bound_account_factories: FactoryBundle,
) -> None:
    user_factory, account_factory, member_factory = await bound_account_factories()

    def _seed(_s: Session) -> tuple[UUID, UUID, UUID]:
        owner = user_factory(email="own1@example.com")
        other = user_factory(email="own1-other@example.com")
        p1 = account_factory(owner_id=owner.id, name="Perso 1")
        p2 = account_factory(owner_id=owner.id, name="Perso 2")
        # Excluded: archived personal, and a shared account the owner is a member of.
        account_factory(owner_id=owner.id, name="Archived", archived_at=datetime.now(tz=UTC))
        shared = account_factory(owner_id=None, name="Commun")
        member_factory(account_id=shared.id, user_id=owner.id)
        member_factory(account_id=shared.id, user_id=other.id)
        return owner.id, p1.id, p2.id

    owner_id, p1_id, p2_id = await household_singleton.run_sync(_seed)

    assert await owned_personal_account_ids(household_singleton, owner_id=owner_id) == {
        p1_id,
        p2_id,
    }


async def test_owned_personal_excludes_other_owner(
    household_singleton: AsyncSession,
    bound_account_factories: FactoryBundle,
) -> None:
    user_factory, account_factory, _ = await bound_account_factories()

    def _seed(_s: Session) -> UUID:
        owner_a = user_factory(email="a@example.com")
        owner_b = user_factory(email="b@example.com")
        account_factory(owner_id=owner_b.id, name="B perso")
        return owner_a.id

    owner_a_id = await household_singleton.run_sync(_seed)

    assert await owned_personal_account_ids(household_singleton, owner_id=owner_a_id) == set()


# ---------------------------------------------------------------------------
# shared_account_ids_with_members_subset
# ---------------------------------------------------------------------------


async def test_shared_subset_all_members_contributors(
    household_singleton: AsyncSession,
    bound_account_factories: FactoryBundle,
) -> None:
    # Compte commun {A,B}, member_ids={A,B,C} → retourné (members ⊆ contribs).
    user_factory, account_factory, member_factory = await bound_account_factories()

    def _seed(_s: Session) -> tuple[UUID, UUID, UUID, UUID]:
        a = user_factory(email="sub-a@example.com")
        b = user_factory(email="sub-b@example.com")
        c = user_factory(email="sub-c@example.com")
        shared = account_factory(owner_id=None, name="AB")
        member_factory(account_id=shared.id, user_id=a.id)
        member_factory(account_id=shared.id, user_id=b.id)
        return a.id, b.id, c.id, shared.id

    a_id, b_id, c_id, shared_id = await household_singleton.run_sync(_seed)

    result = await shared_account_ids_with_members_subset(
        household_singleton, member_ids={a_id, b_id, c_id}
    )
    assert result == {shared_id}


async def test_shared_subset_exact_match(
    household_singleton: AsyncSession,
    bound_account_factories: FactoryBundle,
) -> None:
    # member_ids == members exactement → retourné.
    user_factory, account_factory, member_factory = await bound_account_factories()

    def _seed(_s: Session) -> tuple[UUID, UUID, UUID]:
        a = user_factory(email="ex-a@example.com")
        b = user_factory(email="ex-b@example.com")
        shared = account_factory(owner_id=None, name="AB")
        member_factory(account_id=shared.id, user_id=a.id)
        member_factory(account_id=shared.id, user_id=b.id)
        return a.id, b.id, shared.id

    a_id, b_id, shared_id = await household_singleton.run_sync(_seed)

    result = await shared_account_ids_with_members_subset(
        household_singleton, member_ids={a_id, b_id}
    )
    assert result == {shared_id}


async def test_shared_subset_excludes_account_with_outsider(
    household_singleton: AsyncSession,
    bound_account_factories: FactoryBundle,
) -> None:
    # Compte commun {A,B,C}, member_ids={A,B} → NON retourné (C hors contribs).
    user_factory, account_factory, member_factory = await bound_account_factories()

    def _seed(_s: Session) -> tuple[UUID, UUID]:
        a = user_factory(email="out-a@example.com")
        b = user_factory(email="out-b@example.com")
        c = user_factory(email="out-c@example.com")
        shared = account_factory(owner_id=None, name="ABC")
        member_factory(account_id=shared.id, user_id=a.id, default_share_ratio="0.3333")
        member_factory(account_id=shared.id, user_id=b.id, default_share_ratio="0.3333")
        member_factory(account_id=shared.id, user_id=c.id, default_share_ratio="0.3334")
        return a.id, b.id

    a_id, b_id = await household_singleton.run_sync(_seed)

    result = await shared_account_ids_with_members_subset(
        household_singleton, member_ids={a_id, b_id}
    )
    assert result == set()


async def test_shared_subset_empty_member_ids(
    household_singleton: AsyncSession,
    bound_account_factories: FactoryBundle,
) -> None:
    user_factory, account_factory, member_factory = await bound_account_factories()

    def _seed(_s: Session) -> None:
        a = user_factory(email="empty-a@example.com")
        b = user_factory(email="empty-b@example.com")
        shared = account_factory(owner_id=None, name="AB")
        member_factory(account_id=shared.id, user_id=a.id)
        member_factory(account_id=shared.id, user_id=b.id)

    await household_singleton.run_sync(_seed)

    assert (
        await shared_account_ids_with_members_subset(household_singleton, member_ids=set()) == set()
    )


async def test_shared_subset_excludes_archived(
    household_singleton: AsyncSession,
    bound_account_factories: FactoryBundle,
) -> None:
    user_factory, account_factory, member_factory = await bound_account_factories()

    def _seed(_s: Session) -> tuple[UUID, UUID]:
        a = user_factory(email="arch-a@example.com")
        b = user_factory(email="arch-b@example.com")
        shared = account_factory(owner_id=None, name="AB", archived_at=datetime.now(tz=UTC))
        member_factory(account_id=shared.id, user_id=a.id)
        member_factory(account_id=shared.id, user_id=b.id)
        return a.id, b.id

    a_id, b_id = await household_singleton.run_sync(_seed)

    result = await shared_account_ids_with_members_subset(
        household_singleton, member_ids={a_id, b_id}
    )
    assert result == set()


async def test_shared_subset_excludes_account_without_members(
    household_singleton: AsyncSession,
    bound_account_factories: FactoryBundle,
) -> None:
    # Compte commun **orphelin** (0 member) : exclu, malgré la vacuité de la
    # clause `notin_`. L'invariant `shared ⇒ ≥2 members` est garanti au service,
    # pas par un CHECK DB → le helper ne doit pas l'inclure (fail-closed, D7).
    user_factory, account_factory, _ = await bound_account_factories()

    def _seed(_s: Session) -> UUID:
        a = user_factory(email="orphan-a@example.com")
        account_factory(owner_id=None, name="Orphelin")  # aucun AccountMember
        return a.id

    a_id = await household_singleton.run_sync(_seed)

    result = await shared_account_ids_with_members_subset(household_singleton, member_ids={a_id})
    assert result == set()


async def test_shared_subset_excludes_personal(
    household_singleton: AsyncSession,
    bound_account_factories: FactoryBundle,
) -> None:
    # Un compte PERSONNEL (owner non NULL) n'est jamais retourné par le helper shared.
    user_factory, account_factory, _ = await bound_account_factories()

    def _seed(_s: Session) -> UUID:
        owner = user_factory(email="perso-only@example.com")
        account_factory(owner_id=owner.id, name="Perso")
        return owner.id

    owner_id = await household_singleton.run_sync(_seed)

    result = await shared_account_ids_with_members_subset(
        household_singleton, member_ids={owner_id}
    )
    assert result == set()
