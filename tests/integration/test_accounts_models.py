"""Integration tests for `accounts.models` (S05.1, P05.1.3).

Exercise the persisted behaviour the unit tier and the level-1 snapshot
cannot reach: the `account_type` ENUM value round-trip (`values_callable`),
the `ON DELETE RESTRICT`/`CASCADE` FKs, the `(account_id, user_id)` unique,
and that `default_share_ratio` reads back as an exact `Decimal` (never a
float). Pure `flush` + rollback isolation (`auth_schema`/`db_session`) —
the FK/unique violations surface at `flush` because they are DB-level.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from decimal import Decimal

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.accounts.domain import AccountType
from backend.modules.accounts.models import (
    HOUSEHOLD_SINGLETON_UUID,
    Account,
    AccountMember,
)
from backend.modules.auth.models import User

# Every test here inserts an `Account`, whose `household_id` FK requires the
# singleton `household` row to exist (ADR 0010); seed it for the whole module.
pytestmark = pytest.mark.usefixtures("household_singleton")


async def test_personal_account_persists(
    auth_schema: AsyncSession,
    bound_user_factory: Callable[..., Awaitable[User]],
) -> None:
    user = await bound_user_factory()
    account = Account(
        name="Compte courant",
        type=AccountType.COURANT,
        currency="EUR",
        owner_id=user.id,
    )
    auth_schema.add(account)
    await auth_schema.flush()
    account_id = account.id

    auth_schema.expire_all()
    reloaded = (
        await auth_schema.execute(select(Account).where(Account.id == account_id))
    ).scalar_one()
    # `household_id` defaults to the singleton via the column default.
    assert reloaded.household_id == HOUSEHOLD_SINGLETON_UUID
    assert reloaded.created_at is not None
    assert reloaded.archived_at is None


async def test_account_type_round_trips_all_five(
    auth_schema: AsyncSession,
    bound_user_factory: Callable[..., Awaitable[User]],
) -> None:
    user = await bound_user_factory()
    # Capture `id` before the loop: the `expire_all()` below also expires
    # `user`, so re-reading `user.id` on the next iteration would emit a sync
    # lazy SELECT outside the async greenlet (MissingGreenlet).
    owner_id = user.id
    for member in AccountType:
        account = Account(
            name=f"acct-{member.value}",
            type=member,
            currency="EUR",
            owner_id=owner_id,
        )
        auth_schema.add(account)
        await auth_schema.flush()
        account_id = account.id

        # `expire_all()` is indispensable: without it the identity-map would
        # return the in-memory object without re-hydrating from Postgres, so
        # `reloaded.type == member` would test nothing.
        auth_schema.expire_all()
        reloaded = (
            await auth_schema.execute(select(Account).where(Account.id == account_id))
        ).scalar_one()
        assert reloaded.type == member

        # The load-bearing assertion: the raw stored value is the lowercased
        # ENUM label (the `text()` always crosses the DB), proving
        # `values_callable` drives the mapping rather than the member name.
        raw = (
            await auth_schema.execute(
                text("SELECT type::text FROM accounts WHERE id = :id"),
                {"id": account_id},
            )
        ).scalar_one()
        assert raw == member.value


async def test_default_share_ratio_is_decimal_not_float(
    auth_schema: AsyncSession,
    bound_user_factory: Callable[..., Awaitable[User]],
) -> None:
    user = await bound_user_factory()
    account = Account(name="Commun", type=AccountType.COURANT, currency="EUR")
    auth_schema.add(account)
    await auth_schema.flush()

    member = AccountMember(
        account_id=account.id,
        user_id=user.id,
        default_share_ratio=Decimal("0.3333"),
    )
    auth_schema.add(member)
    await auth_schema.flush()
    member_id = member.id

    auth_schema.expire_all()
    reloaded = (
        await auth_schema.execute(select(AccountMember).where(AccountMember.id == member_id))
    ).scalar_one()
    assert isinstance(reloaded.default_share_ratio, Decimal)
    assert reloaded.default_share_ratio == Decimal("0.3333")


async def test_duplicate_member_violates_unique(
    auth_schema: AsyncSession,
    bound_user_factory: Callable[..., Awaitable[User]],
) -> None:
    user = await bound_user_factory()
    account = Account(name="Commun", type=AccountType.COURANT, currency="EUR")
    auth_schema.add(account)
    await auth_schema.flush()

    auth_schema.add(
        AccountMember(account_id=account.id, user_id=user.id, default_share_ratio=Decimal("0.5000"))
    )
    await auth_schema.flush()
    auth_schema.add(
        AccountMember(account_id=account.id, user_id=user.id, default_share_ratio=Decimal("0.5000"))
    )
    with pytest.raises(IntegrityError):
        await auth_schema.flush()


async def test_delete_user_owning_account_raises_restrict(
    auth_schema: AsyncSession,
    bound_user_factory: Callable[..., Awaitable[User]],
) -> None:
    # Decision F02: an owner is disabled, never hard-deleted — RESTRICT makes
    # the delete raise rather than orphan or silently reassign the account.
    user = await bound_user_factory()
    account = Account(name="Perso", type=AccountType.COURANT, currency="EUR", owner_id=user.id)
    auth_schema.add(account)
    await auth_schema.flush()

    await auth_schema.delete(user)
    with pytest.raises(IntegrityError):
        await auth_schema.flush()


async def test_delete_user_member_raises_restrict(
    auth_schema: AsyncSession,
    bound_user_factory: Callable[..., Awaitable[User]],
) -> None:
    user = await bound_user_factory()
    account = Account(name="Commun", type=AccountType.COURANT, currency="EUR")
    auth_schema.add(account)
    await auth_schema.flush()
    auth_schema.add(
        AccountMember(account_id=account.id, user_id=user.id, default_share_ratio=Decimal("1.0000"))
    )
    await auth_schema.flush()

    await auth_schema.delete(user)
    with pytest.raises(IntegrityError):
        await auth_schema.flush()


async def test_delete_account_cascades_members(
    auth_schema: AsyncSession,
    bound_user_factory: Callable[..., Awaitable[User]],
) -> None:
    u1 = await bound_user_factory()
    u2 = await bound_user_factory()
    account = Account(name="Commun", type=AccountType.COURANT, currency="EUR")
    auth_schema.add(account)
    await auth_schema.flush()
    account_id = account.id
    auth_schema.add_all(
        [
            AccountMember(
                account_id=account_id, user_id=u1.id, default_share_ratio=Decimal("0.5000")
            ),
            AccountMember(
                account_id=account_id, user_id=u2.id, default_share_ratio=Decimal("0.5000")
            ),
        ]
    )
    await auth_schema.flush()

    await auth_schema.delete(account)
    await auth_schema.flush()

    count = (
        await auth_schema.execute(
            text("SELECT count(*) FROM account_members WHERE account_id = :id"),
            {"id": account_id},
        )
    ).scalar_one()
    assert count == 0


async def test_account_member_factory_builds_shared_account(
    auth_schema: AsyncSession,
    bound_account_factories: Callable[[], Awaitable[tuple[type, type, type]]],
) -> None:
    # Livrable observable: the factories instantiate a shared account end to
    # end. The three factories share one session (`bound_account_factories`),
    # so the persisted rows live in one identity-map / one flush boundary.
    user_factory, account_factory, member_factory = await bound_account_factories()

    def _build(_sync_session: object) -> object:
        u1 = user_factory()
        u2 = user_factory()
        account = account_factory(owner_id=None)
        # Explicit ratios summing to 1 (the factory default 0.5000 is only
        # valid for 2 members — here it happens to fit, but pin it anyway).
        member_factory(account_id=account.id, user_id=u1.id, default_share_ratio=Decimal("0.6000"))
        member_factory(account_id=account.id, user_id=u2.id, default_share_ratio=Decimal("0.4000"))
        return account.id

    account_id = await auth_schema.run_sync(_build)

    count = (
        await auth_schema.execute(
            text("SELECT count(*) FROM account_members WHERE account_id = :id"),
            {"id": account_id},
        )
    ).scalar_one()
    assert count == 2
