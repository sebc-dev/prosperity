"""Fixtures shared by integration tests.

Provides a `db_session` async SQLAlchemy session backed by a Postgres
container managed by testcontainers. Tests opt in by depending on the
fixture; each test runs in its own transaction that is rolled back at
teardown so state never leaks across tests.

The container fixture (`postgres_container`) and the **real-commit**
stack (`committed_engine`, `committed_sessionmaker`, `committed_client`,
`_clean_committed_db`) live in the root `tests/conftest.py` so the `e2e`
tier — a sibling package — can resolve them too (P-E2E.1 hoist). They
remain available here by ancestor inheritance, unchanged.

If Docker is not reachable on the host (typical local dev without Docker
Desktop's WSL integration enabled), `postgres_container` skips —
keeping the unit/http tiers green while the integration tier defers to
CI where Docker is available.

Exposes (local to this tier):
- `db_engine` / `db_session` — rollback-on-teardown isolation
- `auth_schema` — db_session with every persisted-module table materialised
- `bound_user_factory` — factory that creates a `User` against `db_session`
- `async_client` — httpx AsyncClient bound to the FastAPI app, with
  `get_db` overridden to yield the test's `db_session` (savepoint mode, so
  the transactional rollback teardown reverts everything).
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator
from typing import cast

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import Session
from testcontainers.postgres import PostgresContainer

# Side-effect import: registers `bank_account_external_refs` on `Base.metadata`
# (S12.1, #176) so `auth_schema`'s `create_all` materialises the banking table
# and the migration-parity test can diff it against the snapshot.
import backend.modules.banking.models  # noqa: F401  # pyright: ignore[reportUnusedImport]

# Side-effect import: registers both `debts` tables (`debts` + `share_requests`)
# on `Base.metadata`. REQUIRED here (not optional like transactions, which the
# factory imports pull in): S09.1 activates the FK
# `transactions.share_request_id → share_requests.id`, so `auth_schema`'s
# `create_all` cannot resolve the `Transaction` FK target table unless
# `share_requests` is registered first.
import backend.modules.debts.models  # noqa: F401  # pyright: ignore[reportUnusedImport]
from backend.main import app

# Importing `Household` also registers every accounts table on `Base.metadata`
# (the side-effect `auth_schema`'s `create_all` relies on).
from backend.modules.accounts.models import Household
from backend.modules.accounts.service.household import invalidate_household_cache
from backend.modules.auth.models import User
from backend.modules.budget.models import Category

# `transactions`/`splits` register on `Base.metadata` via the factory imports
# below (`tests.factories.sqlalchemy`), so `auth_schema`'s `create_all`
# materialises them — no separate side-effect import needed here.
from backend.shared.db import get_db
from backend.shared.models import Base
from tests.factories.sqlalchemy import (
    AccountFactory,
    AccountMemberFactory,
    CategoryFactory,
    SplitFactory,
    TransactionFactory,
    UserFactory,
)

_BoundTxFactories = Callable[
    [],
    Awaitable[
        tuple[type[UserFactory], type[AccountFactory], type[TransactionFactory], type[SplitFactory]]
    ],
]

_BoundAccountFactories = Callable[
    [],
    Awaitable[tuple[type[UserFactory], type[AccountFactory], type[AccountMemberFactory]]],
]


@pytest.fixture(autouse=True)
def _reset_household_cache() -> Iterator[None]:  # pyright: ignore[reportUnusedFunction]
    """Reset the process-local `get_household` singleton cache around every test.

    `get_household` (accounts) memoises the singleton row process-wide; the OFX
    commit currency gate reads it. Without a reset, a test could read a household
    seeded — and rolled back — by a previous test (stale-cache false positive on
    `household_not_initialized` / `currency_mismatch`). Hoisted here from
    `test_imports_commit.py` (S12.5) so the e2e tier is protected too. Idempotent
    and cheap, so applying it tier-wide is harmless.
    """
    invalidate_household_cache()
    yield
    invalidate_household_cache()


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def db_engine(postgres_container: PostgresContainer) -> AsyncIterator[object]:
    # `statement_cache_size=0` disables asyncpg's server-side prepared-statement
    # cache. This session-scoped pool shares one database with the module-scoped
    # `committed_engine`, whose teardown runs `Base.metadata.drop_all` and a later
    # module recreates the schema — the enum/composite types come back with new
    # OIDs. A pooled connection here would otherwise replay a cached plan pinned to
    # a dropped OID and raise `InternalServerError: cache lookup failed for type …`.
    # Re-preparing every statement is the price; correctness across the cross-engine
    # DDL churn is the gain (tests only — production has a single engine, no churn).
    engine = create_async_engine(
        postgres_container.get_connection_url(),
        future=True,
        connect_args={"statement_cache_size": 0},
    )
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest_asyncio.fixture(loop_scope="session")
async def db_session(db_engine) -> AsyncIterator[AsyncSession]:
    """Per-test async session with rollback-on-teardown isolation."""
    async with db_engine.connect() as connection:
        transaction = await connection.begin()
        session_factory = async_sessionmaker(bind=connection, expire_on_commit=False)
        async with session_factory() as session:
            try:
                yield session
            finally:
                await transaction.rollback()


@pytest_asyncio.fixture(loop_scope="session")
async def auth_schema(db_session: AsyncSession) -> AsyncSession:
    """Create every persisted-module table on the test's transactional connection.

    Historically scoped to the auth tables; with the shared `Base`
    `create_all` materialises every module's tables in one shot. The
    name is preserved so S02.* consumers keep working; new callers
    should treat it as "all-modules schema". Setup is cheap (one DDL
    round-trip) and the transaction-level rollback teardown still
    guarantees per-test isolation.
    """
    conn = await db_session.connection()
    await conn.run_sync(Base.metadata.create_all)
    return db_session


@pytest_asyncio.fixture(loop_scope="session")
async def household_singleton(auth_schema: AsyncSession) -> AsyncSession:
    """Seed the singleton `household` row (ADR 0010).

    `accounts.household_id` FK-references `household.id` and defaults to the
    singleton UUID, so every `Account` insert needs the row to exist first —
    without it the integration tier fails `fk_accounts_household_id_household`.
    Seeded on the transactional `auth_schema` session, so the rollback
    teardown removes it per test. `Household.id` defaults to the singleton
    UUID, so no explicit id is passed.
    """

    def _seed(sync_session: Session) -> None:
        sync_session.add(Household(name="Test Household", base_currency="EUR"))

    await auth_schema.run_sync(_seed)
    return auth_schema


@pytest_asyncio.fixture(loop_scope="session")
async def bound_user_factory(
    auth_schema: AsyncSession,
) -> Callable[..., Awaitable[User]]:
    """Async helper that persists a `User` against the test's session.

    Extracted from the `_make_user` helper that lived in
    `test_refresh_tokens.py` once S02.4 introduced a second consumer
    (auth routes tests). Kept here (not in the global `tests/conftest.py`)
    so the unit tier never pulls in `db_session`.
    """

    async def _make_user(**overrides: object) -> User:
        def _create(sync_session: Session) -> User:
            UserFactory._meta.sqlalchemy_session = sync_session  # type: ignore[attr-defined]
            return cast(User, UserFactory(**overrides))

        return await auth_schema.run_sync(_create)

    return _make_user


@pytest_asyncio.fixture(loop_scope="session")
async def bound_category_factory(
    auth_schema: AsyncSession,
) -> Callable[..., Awaitable[Category]]:
    """Persist a `Category` against the test's session (gabarit
    `bound_user_factory`). Pass `parent_id=<id>` for a child; omit for a root.

    `Category` has no FK to `household`/`users`, so a single factory suffices
    (no multi-factory `bound_*_factories` as for shared accounts).
    """

    async def _make_category(**overrides: object) -> Category:
        def _create(sync_session: Session) -> Category:
            CategoryFactory._meta.sqlalchemy_session = sync_session  # type: ignore[attr-defined]
            return cast(Category, CategoryFactory(**overrides))

        return await auth_schema.run_sync(_create)

    return _make_category


@pytest_asyncio.fixture(loop_scope="session")
async def bound_account_factories(
    auth_schema: AsyncSession,
) -> Callable[
    [], Awaitable[tuple[type[UserFactory], type[AccountFactory], type[AccountMemberFactory]]]
]:
    """Bind User/Account/AccountMember factories to the test's session.

    Mirrors `bound_user_factory` but binds the three factories an accounts
    integration test needs onto a *single* sync session, so persisted rows
    share one identity-map / one flush boundary. `bound_user_factory` binds
    only `UserFactory`; building a shared account needs all three on the same
    session, otherwise objects attach to divergent sessions and the flush
    breaks.
    """

    async def _bind() -> tuple[type[UserFactory], type[AccountFactory], type[AccountMemberFactory]]:
        def _do(sync_session: Session) -> None:
            for factory in (UserFactory, AccountFactory, AccountMemberFactory):
                factory._meta.sqlalchemy_session = sync_session  # type: ignore[attr-defined]

        await auth_schema.run_sync(_do)
        return UserFactory, AccountFactory, AccountMemberFactory

    return _bind


@pytest_asyncio.fixture(loop_scope="session")
async def bound_transaction_factories(
    household_singleton: AsyncSession,
) -> Callable[
    [],
    Awaitable[
        tuple[type[UserFactory], type[AccountFactory], type[TransactionFactory], type[SplitFactory]]
    ],
]:
    """Bind User/Account/Transaction/Split factories to the test's session.

    Mirrors `bound_account_factories`: a transaction needs a `User`
    (`created_by` RESTRICT) and an `Account` (`account_id` RESTRICT) as real
    FK rows, and `TransactionFactory`'s post-generation splits persist via
    `SplitFactory` — so all four must share one sync session / one flush
    boundary, otherwise objects attach to divergent sessions and the flush
    breaks. Depends on `household_singleton` (the account needs the singleton
    row to exist for its `household_id` FK).

    `CategoryFactory` is bound on the SAME session too (though not returned):
    `TransactionFactory`'s default canonical-form-B pair auto-creates a
    `Category` for its classification leg, which must persist via this session.
    """

    async def _bind() -> tuple[
        type[UserFactory], type[AccountFactory], type[TransactionFactory], type[SplitFactory]
    ]:
        def _do(sync_session: Session) -> None:
            for factory in (
                UserFactory,
                AccountFactory,
                CategoryFactory,
                TransactionFactory,
                SplitFactory,
            ):
                factory._meta.sqlalchemy_session = sync_session  # type: ignore[attr-defined]

        await household_singleton.run_sync(_do)
        return UserFactory, AccountFactory, TransactionFactory, SplitFactory

    return _bind


@pytest_asyncio.fixture(loop_scope="session")
async def seed_account(
    household_singleton: AsyncSession,
    bound_transaction_factories: _BoundTxFactories,
) -> Callable[[], Awaitable[tuple[uuid.UUID, uuid.UUID]]]:
    """Seed a `(account_id, owner user_id)` pair for transaction tests.

    Shared by every transaction integration test that needs a real `Account` +
    its owner `User` as FK rows (was copy-pasted as a local `_seed_account`
    helper in `test_overflow_socle_lock.py` / `test_transactions_editable_event.py`
    before S11.1 review).
    """

    async def _seed() -> tuple[uuid.UUID, uuid.UUID]:
        user_factory, account_factory, _tx, _split = await bound_transaction_factories()

        def _build(_sync: object) -> tuple[uuid.UUID, uuid.UUID]:
            user = user_factory()
            return account_factory(owner_id=user.id).id, user.id

        return await household_singleton.run_sync(_build)

    return _seed


@pytest_asyncio.fixture(loop_scope="session")
async def seed_personal_account(
    household_singleton: AsyncSession,
    bound_account_factories: _BoundAccountFactories,
) -> Callable[..., Awaitable[tuple[uuid.UUID, uuid.UUID]]]:
    """Seed a `(user_id, account_id)` owner pair for the OFX-import route tests.

    Replaces the `_make_user`/`_make_account` helpers that were copy-pasted into
    `test_imports_routes_preview.py` / `_routes_link.py` (review S12.4): one
    factory-backed body instead of hand-rolled ORM inserts. `role` lets a test
    build an admin owner; the account is a personal `COURANT` in EUR (factory
    defaults). Companion of `seed_account` (which returns the reversed tuple and
    pulls in the transaction-factory bundle).
    """

    async def _seed(*, role: str = "member") -> tuple[uuid.UUID, uuid.UUID]:
        user_factory, account_factory, _member = await bound_account_factories()

        def _build(_sync: object) -> tuple[uuid.UUID, uuid.UUID]:
            user = user_factory(role=role)
            return user.id, account_factory(owner_id=user.id).id

        return await household_singleton.run_sync(_build)

    return _seed


@pytest_asyncio.fixture(loop_scope="session")
async def seed_tx(
    household_singleton: AsyncSession,
    bound_transaction_factories: _BoundTxFactories,
) -> Callable[..., Awaitable[uuid.UUID]]:
    """Seed a balanced same-account transaction pair in `state` (factory sets the
    column directly), returning its id.

    Companion of `seed_account`; both replace the per-file `_seed_account`/`_seed_tx`
    helpers duplicated across the transaction integration tests.
    """

    async def _seed(*, account_id: uuid.UUID, user_id: uuid.UUID, state: str) -> uuid.UUID:
        _u, _a, tx_factory, _split = await bound_transaction_factories()

        def _build(_sync: object) -> uuid.UUID:
            return tx_factory(account_id=account_id, created_by=user_id, state=state).id

        return await household_singleton.run_sync(_build)

    return _seed


@pytest_asyncio.fixture(loop_scope="session")
async def async_client(auth_schema: AsyncSession) -> AsyncIterator[AsyncClient]:
    """httpx AsyncClient wired to the FastAPI app with `get_db` overridden.

    Mirrors prod `get_db` semantics: each request gets its **own** session
    bound to the test's connection, with `join_transaction_mode="create_savepoint"`
    so request-level commit/rollback maps to SAVEPOINT release/revert
    inside the outer test transaction. The test's setup writes (via
    `auth_schema` and `bound_user_factory`) stay in the outer transaction
    untouched, so a request that 4xx-rollbacks does not wipe schema or
    fixture users.

    Critically, this means `service.rotate()`'s commit-inside-service
    (ADR 0015) actually survives the route's exception handler in
    tests — the bug fixed in #58 was masked by the previous override
    that yielded the shared session without any commit/rollback wrap.
    `try/finally` + `pop(get_db, None)` so adjacent fixtures that
    register their own overrides are not clobbered.
    """
    connection = await auth_schema.connection()
    request_session_factory = async_sessionmaker(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )

    async def _override_get_db() -> AsyncIterator[AsyncSession]:
        async with request_session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = _override_get_db
    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client
    finally:
        app.dependency_overrides.pop(get_db, None)
