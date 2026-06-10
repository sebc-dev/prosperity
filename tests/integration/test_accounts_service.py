"""Integration tests for `accounts.service.accounts` (S05.2, P05.2.2).

Drives `create_personal` / `create_shared` against a real Postgres so the
DB-level behaviour fires: the `Account`/`AccountMember` INSERTs, the
`Numeric(5, 4)` → `Decimal` round-trip on `default_share_ratio`, and — on
`committed_engine` — the no-commit contract (flush-only, ADR 0015) and the
atomicity of the multi-row shared-account write (a failing member INSERT
persists nothing).

Two tiers:

* Rollback-isolated (`auth_schema` / `bound_user_factory`): persistence and
  pre-write rejections. Each test seeds its **own** initialised household —
  `household_singleton` is deliberately NOT reused (it seeds an
  *un*-initialised row, so `get_household` would raise
  `HouseholdNotInitializedError`).
* Real-commit (`committed_engine`): atomicity / no-commit / rollback, verified
  from an independent session so we prove nothing was truly persisted.

`_reset_household_cache` (autouse) brackets **every** test — including the
`committed_engine` ones — because `get_household`'s cache is process-local and
survives rollbacks; without bracketing invalidation a household primed by one
test would leak into the next.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from backend.modules.accounts.domain import (
    AccountType,
    CurrencyMismatchError,
    DuplicateMemberError,
    MemberShare,
    ShareRatioSumError,
    TooFewMembersError,
)
from backend.modules.accounts.models import Account, AccountMember, Household
from backend.modules.accounts.service.accounts import create_personal, create_shared
from backend.modules.accounts.service.household import (
    HouseholdNotInitializedError,
    invalidate_household_cache,
)
from backend.modules.auth.models import User, UserRole

UserMaker = Callable[..., Awaitable[User]]


# ---------------------------------------------------------------------------
# Rollback-isolated tier helpers (auth_schema)
# ---------------------------------------------------------------------------


async def _seed_initialized_household(session: AsyncSession, *, base_currency: str = "EUR") -> None:
    """Seed an *initialised* singleton so `get_household` resolves (not raises)."""
    session.add(
        Household(
            name="Test Household",
            base_currency=base_currency,
            initialized_at=datetime.now(tz=UTC),
        )
    )
    await session.flush()


async def _count(session: AsyncSession, model: type[Account] | type[AccountMember]) -> int:
    return (await session.execute(select(func.count()).select_from(model))).scalar_one()


# ---------------------------------------------------------------------------
# create_personal — persistence
# ---------------------------------------------------------------------------


async def test_create_personal_persists_account_without_members(
    auth_schema: AsyncSession, bound_user_factory: UserMaker
) -> None:
    await _seed_initialized_household(auth_schema)
    owner = await bound_user_factory(email="owner@example.com")

    account = await create_personal(
        auth_schema,
        owner_id=owner.id,
        name="Compte courant",
        type=AccountType.COURANT,
        currency="EUR",
    )

    assert account.owner_id == owner.id
    assert account.currency == "EUR"
    assert account.type == AccountType.COURANT
    member_count = (
        await auth_schema.execute(
            select(func.count())
            .select_from(AccountMember)
            .where(AccountMember.account_id == account.id)
        )
    ).scalar_one()
    assert member_count == 0


async def test_create_personal_returns_flushed_account(
    auth_schema: AsyncSession, bound_user_factory: UserMaker
) -> None:
    await _seed_initialized_household(auth_schema)
    owner = await bound_user_factory(email="owner2@example.com")

    account = await create_personal(
        auth_schema,
        owner_id=owner.id,
        name="Livret",
        type=AccountType.LIVRET,
        currency="EUR",
    )

    # PK assigned at flush — proves the service flushed, not merely added.
    assert account.id is not None


# ---------------------------------------------------------------------------
# create_shared — persistence
# ---------------------------------------------------------------------------


async def test_create_shared_persists_account_and_members(
    auth_schema: AsyncSession, bound_user_factory: UserMaker
) -> None:
    await _seed_initialized_household(auth_schema)
    u1 = await bound_user_factory(email="m1@example.com")
    u2 = await bound_user_factory(email="m2@example.com")
    members = [
        MemberShare(user_id=u1.id, ratio=Decimal("0.5000")),
        MemberShare(user_id=u2.id, ratio=Decimal("0.5000")),
    ]

    account = await create_shared(
        auth_schema,
        members=members,
        name="Compte commun",
        type=AccountType.COURANT,
        currency="EUR",
    )

    assert account.owner_id is None
    # Capture ids before `expire_all`: afterwards any ORM attribute access on
    # these instances would lazy-load and raise MissingGreenlet (async).
    account_id = account.id
    expected_user_ids = {u1.id, u2.id}
    auth_schema.expire_all()  # force a real DB read of the Numeric(5,4) column
    rows = (
        (
            await auth_schema.execute(
                select(AccountMember).where(AccountMember.account_id == account_id)
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == 2
    assert {r.user_id for r in rows} == expected_user_ids
    for r in rows:
        assert isinstance(r.default_share_ratio, Decimal)
        assert r.default_share_ratio == Decimal("0.5000")


async def test_create_shared_three_members(
    auth_schema: AsyncSession, bound_user_factory: UserMaker
) -> None:
    await _seed_initialized_household(auth_schema)
    u1 = await bound_user_factory(email="t1@example.com")
    u2 = await bound_user_factory(email="t2@example.com")
    u3 = await bound_user_factory(email="t3@example.com")
    members = [
        MemberShare(user_id=u1.id, ratio=Decimal("0.5000")),
        MemberShare(user_id=u2.id, ratio=Decimal("0.2500")),
        MemberShare(user_id=u3.id, ratio=Decimal("0.2500")),
    ]

    account = await create_shared(
        auth_schema,
        members=members,
        name="Trio",
        type=AccountType.COURANT,
        currency="EUR",
    )

    account_id = account.id  # capture before expire_all (avoid async lazy-load)
    auth_schema.expire_all()
    rows = (
        (
            await auth_schema.execute(
                select(AccountMember).where(AccountMember.account_id == account_id)
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == 3
    assert sum(r.default_share_ratio for r in rows) == Decimal("1.0000")


# ---------------------------------------------------------------------------
# Pre-write rejections (validation runs before any add)
# ---------------------------------------------------------------------------


async def test_create_personal_rejects_currency_mismatch_before_write(
    auth_schema: AsyncSession,
) -> None:
    await _seed_initialized_household(auth_schema)  # base EUR

    with pytest.raises(CurrencyMismatchError):
        await create_personal(
            auth_schema,
            owner_id=uuid.uuid4(),
            name="Devise",
            type=AccountType.COURANT,
            currency="USD",
        )

    assert await _count(auth_schema, Account) == 0


async def test_create_shared_rejects_bad_ratio_sum_before_write(
    auth_schema: AsyncSession,
) -> None:
    await _seed_initialized_household(auth_schema)
    members = [
        MemberShare(user_id=uuid.uuid4(), ratio=Decimal("0.5000")),
        MemberShare(user_id=uuid.uuid4(), ratio=Decimal("0.4999")),
    ]

    with pytest.raises(ShareRatioSumError):
        await create_shared(
            auth_schema,
            members=members,
            name="MauvaiseSomme",
            type=AccountType.COURANT,
            currency="EUR",
        )

    assert await _count(auth_schema, Account) == 0
    assert await _count(auth_schema, AccountMember) == 0


async def test_create_shared_rejects_single_member(auth_schema: AsyncSession) -> None:
    await _seed_initialized_household(auth_schema)
    members = [MemberShare(user_id=uuid.uuid4(), ratio=Decimal("1.0000"))]

    with pytest.raises(TooFewMembersError):
        await create_shared(
            auth_schema,
            members=members,
            name="Solo",
            type=AccountType.COURANT,
            currency="EUR",
        )

    assert await _count(auth_schema, Account) == 0
    assert await _count(auth_schema, AccountMember) == 0


async def test_create_shared_rejects_duplicate_member_before_write(
    auth_schema: AsyncSession, bound_user_factory: UserMaker
) -> None:
    # The same user listed twice (ratios summing to 1) is rejected by the pure
    # validator *before* any write — a clean DuplicateMemberError (422 family),
    # not the raw IntegrityError the unique constraint would raise at flush.
    await _seed_initialized_household(auth_schema)
    u1 = await bound_user_factory(email="dup@example.com")
    members = [
        MemberShare(user_id=u1.id, ratio=Decimal("0.5000")),
        MemberShare(user_id=u1.id, ratio=Decimal("0.5000")),
    ]

    with pytest.raises(DuplicateMemberError):
        await create_shared(
            auth_schema,
            members=members,
            name="Doublon",
            type=AccountType.COURANT,
            currency="EUR",
        )

    assert await _count(auth_schema, Account) == 0
    assert await _count(auth_schema, AccountMember) == 0


async def test_create_personal_raises_when_household_not_initialized(
    household_singleton: AsyncSession,
) -> None:
    # `household_singleton` seeds the row WITHOUT `initialized_at` (NULL);
    # `get_household` treats that as "not set up" and raises before any write.
    with pytest.raises(HouseholdNotInitializedError):
        await create_personal(
            household_singleton,
            owner_id=uuid.uuid4(),
            name="PasDeSetup",
            type=AccountType.COURANT,
            currency="EUR",
        )

    assert await _count(household_singleton, Account) == 0


# ---------------------------------------------------------------------------
# Real-commit tier (independent sessions on committed_engine)
# ---------------------------------------------------------------------------


async def _seed_committed_household(sm: async_sessionmaker[AsyncSession]) -> None:
    async with sm() as session:
        session.add(
            Household(
                name="Committed Household",
                base_currency="EUR",
                initialized_at=datetime.now(tz=UTC),
            )
        )
        await session.commit()


async def _seed_committed_user(sm: async_sessionmaker[AsyncSession], *, email: str) -> uuid.UUID:
    async with sm() as session:
        user = User(
            email=email,
            password_hash="x" * 60,
            display_name=email.split("@", 1)[0],
            role=UserRole.MEMBER,
        )
        session.add(user)
        await session.flush()
        user_id = user.id
        await session.commit()
    return user_id


@pytest.mark.usefixtures("_clean_committed_db")
async def test_create_does_not_commit(committed_engine: AsyncEngine) -> None:
    # Flush-only contract (ADR 0015): the service never commits, so an
    # independent session must not see the account once the caller's session
    # closes without committing (rolling back).
    sm = async_sessionmaker(committed_engine, expire_on_commit=False)
    await _seed_committed_household(sm)
    owner = await _seed_committed_user(sm, email="owner@example.com")
    invalidate_household_cache()  # seed-committed → invalidate → service (strict order)

    async with sm() as session:
        account = await create_personal(
            session,
            owner_id=owner,
            name="Perso",
            type=AccountType.COURANT,
            currency="EUR",
        )
        assert account.id is not None
        # Deliberately no commit — closing the session rolls back.

    async with sm() as session:
        count = (await session.execute(select(func.count()).select_from(Account))).scalar_one()
        assert count == 0


@pytest.mark.usefixtures("_clean_committed_db")
async def test_create_shared_is_atomic_on_member_failure(committed_engine: AsyncEngine) -> None:
    # A second member with a non-existent user_id violates
    # fk_account_members_user_id_users at the 2nd flush. Because both INSERTs
    # share one transaction (no intermediate commit), the whole creation is
    # discarded: 0 accounts AND 0 members, verified from a fresh session.
    sm = async_sessionmaker(committed_engine, expire_on_commit=False)
    await _seed_committed_household(sm)
    real_user = await _seed_committed_user(sm, email="real@example.com")
    invalidate_household_cache()
    members = [
        MemberShare(user_id=real_user, ratio=Decimal("0.5000")),
        MemberShare(user_id=uuid.uuid4(), ratio=Decimal("0.5000")),  # no such user → FK fails
    ]

    async with sm() as session:
        with pytest.raises(IntegrityError):
            await create_shared(
                session,
                members=members,
                name="Atomic",
                type=AccountType.COURANT,
                currency="EUR",
            )
        await session.rollback()

    async with sm() as session:
        acc_count = (await session.execute(select(func.count()).select_from(Account))).scalar_one()
        mem_count = (
            await session.execute(select(func.count()).select_from(AccountMember))
        ).scalar_one()
        assert acc_count == 0
        assert mem_count == 0


@pytest.mark.usefixtures("_clean_committed_db")
async def test_create_rollback_discards_full_creation(committed_engine: AsyncEngine) -> None:
    # An explicit rollback after a successful create_shared annuls the full
    # creation (account + every member) — the acceptance criterion that
    # rollback discards the complete write.
    sm = async_sessionmaker(committed_engine, expire_on_commit=False)
    await _seed_committed_household(sm)
    u1 = await _seed_committed_user(sm, email="r1@example.com")
    u2 = await _seed_committed_user(sm, email="r2@example.com")
    invalidate_household_cache()
    members = [
        MemberShare(user_id=u1, ratio=Decimal("0.5000")),
        MemberShare(user_id=u2, ratio=Decimal("0.5000")),
    ]

    async with sm() as session:
        account = await create_shared(
            session,
            members=members,
            name="Rollback",
            type=AccountType.COURANT,
            currency="EUR",
        )
        assert account.id is not None
        await session.rollback()

    async with sm() as session:
        acc_count = (await session.execute(select(func.count()).select_from(Account))).scalar_one()
        mem_count = (
            await session.execute(select(func.count()).select_from(AccountMember))
        ).scalar_one()
        assert acc_count == 0
        assert mem_count == 0
