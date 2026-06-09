"""Integration tests for `banking.service.external_refs` (S12.1, P12.1.2).

Exercise `find_internal_account` / `link` against testcontainers Postgres:
link→find round-trip, unknown ref → `None`, double-link rejected (service
pre-check, D6), provider isolation/validation, FK refusal (no account created),
and the flush-only contract (ADR 0015). Gabarit `test_accounts_service.py`.

The DB-enforced uniqueness is proven separately at the model tier
(`test_banking_models.test_duplicate_external_ref_provider_violates_unique`);
here we assert the *typed* application-level rejection.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from backend.modules.accounts.domain import AccountType
from backend.modules.accounts.models import Account, Household
from backend.modules.auth.models import User, UserRole
from backend.modules.banking.models import BankAccountExternalRef, ImportedTransaction
from backend.modules.banking.service.external_refs import (
    AccountAlreadyLinkedError,
    UnknownProviderError,
    find_internal_account,
    link,
)
from backend.modules.banking.service.import_ofx import known_import_hashes

# Every test inserts an `Account`, whose `household_id` FK requires the
# singleton `household` row to exist (ADR 0010); seed it for the whole module.
pytestmark = pytest.mark.usefixtures("household_singleton")


async def _make_account(session: AsyncSession, owner_id: uuid.UUID) -> uuid.UUID:
    account = Account(
        name="Compte courant",
        type=AccountType.COURANT,
        currency="EUR",
        owner_id=owner_id,
    )
    session.add(account)
    await session.flush()
    return account.id


async def test_link_then_find_returns_internal_account(
    auth_schema: AsyncSession,
    bound_user_factory: Callable[..., Awaitable[User]],
) -> None:
    user = await bound_user_factory()
    account_id = await _make_account(auth_schema, user.id)

    ref = await link(
        auth_schema,
        external_ref="XXXX1234",
        internal_account_id=account_id,
        provider="ofx",
    )
    assert ref.id is not None

    found = await find_internal_account(auth_schema, external_ref="XXXX1234", provider="ofx")
    assert found == account_id


async def test_find_unknown_ref_returns_none(auth_schema: AsyncSession) -> None:
    found = await find_internal_account(auth_schema, external_ref="NOPE", provider="ofx")
    assert found is None


async def test_double_link_same_ref_provider_rejected(
    auth_schema: AsyncSession,
    bound_user_factory: Callable[..., Awaitable[User]],
) -> None:
    user = await bound_user_factory()
    account_id = await _make_account(auth_schema, user.id)
    await link(auth_schema, external_ref="XXXX1234", internal_account_id=account_id, provider="ofx")

    # Deterministic typed rejection on the sequential path (D6) — the DB-enforced
    # backstop is proven at the model tier.
    with pytest.raises(AccountAlreadyLinkedError):
        await link(
            auth_schema, external_ref="XXXX1234", internal_account_id=account_id, provider="ofx"
        )


async def test_find_isolates_by_provider(
    auth_schema: AsyncSession,
    bound_user_factory: Callable[..., Awaitable[User]],
) -> None:
    # Two rows, same `external_ref`, distinct providers (inserted by direct ORM
    # add — `link` only validates `"ofx"` in V1). `find_internal_account`
    # discriminates on `provider` (AC #176: composite, never on `external_ref` alone).
    user = await bound_user_factory()
    ofx_account = await _make_account(auth_schema, user.id)
    eb_account = await _make_account(auth_schema, user.id)
    auth_schema.add_all(
        [
            BankAccountExternalRef(
                external_ref="XXXX1234", internal_account_id=ofx_account, provider="ofx"
            ),
            BankAccountExternalRef(
                external_ref="XXXX1234",
                internal_account_id=eb_account,
                provider="enable_banking",
            ),
        ]
    )
    await auth_schema.flush()

    # `find` only accepts `"ofx"` in V1, so the symmetric `"enable_banking"`
    # lookup can't go through the service. A bug dropping the `provider` filter
    # would still be caught here: two rows share `external_ref`, so
    # `scalar_one_or_none` would raise `MultipleResultsFound`.
    assert await find_internal_account(auth_schema, external_ref="XXXX1234", provider="ofx") == (
        ofx_account
    )


async def test_link_unknown_provider_rejected(
    auth_schema: AsyncSession,
    bound_user_factory: Callable[..., Awaitable[User]],
) -> None:
    user = await bound_user_factory()
    account_id = await _make_account(auth_schema, user.id)
    with pytest.raises(UnknownProviderError):
        await link(
            auth_schema, external_ref="XXXX1234", internal_account_id=account_id, provider="sftp"
        )


async def test_find_unknown_provider_rejected(auth_schema: AsyncSession) -> None:
    with pytest.raises(UnknownProviderError):
        await find_internal_account(auth_schema, external_ref="XXXX1234", provider="sftp")


async def test_provider_validation_is_case_sensitive(
    auth_schema: AsyncSession,
    bound_user_factory: Callable[..., Awaitable[User]],
) -> None:
    # Exact membership in `{"ofx"}`, no normalisation: `"OFX"` / `" ofx"` are
    # rejected (pins the expected boundary contract).
    user = await bound_user_factory()
    account_id = await _make_account(auth_schema, user.id)
    for provider in ("OFX", " ofx"):
        with pytest.raises(UnknownProviderError):
            await link(
                auth_schema,
                external_ref="XXXX1234",
                internal_account_id=account_id,
                provider=provider,
            )


async def test_link_then_find_empty_external_ref(
    auth_schema: AsyncSession,
    bound_user_factory: Callable[..., Awaitable[User]],
) -> None:
    # `external_ref=""` is not forbidden by `nullable=False`: decision — allowed
    # at the socle service; the round-trip retrieves the account. An eventual
    # empty-string refusal belongs to the S12.4 boundary, not here.
    user = await bound_user_factory()
    account_id = await _make_account(auth_schema, user.id)
    await link(auth_schema, external_ref="", internal_account_id=account_id, provider="ofx")
    assert await find_internal_account(auth_schema, external_ref="", provider="ofx") == account_id


async def test_known_import_hashes(
    auth_schema: AsyncSession,
    bound_user_factory: Callable[..., Awaitable[User]],
) -> None:
    # Empty input short-circuits BEFORE the query (`IN ()` is invalid SQL) → set().
    assert await known_import_hashes(auth_schema, []) == set()

    user = await bound_user_factory()
    account_id = await _make_account(auth_schema, user.id)
    auth_schema.add_all(
        [
            ImportedTransaction(account_id=account_id, import_hash="hash-a", source="ofx"),
            ImportedTransaction(account_id=account_id, import_hash="hash-b", source="ofx"),
        ]
    )
    await auth_schema.flush()

    # All known.
    assert await known_import_hashes(auth_schema, ["hash-a", "hash-b"]) == {"hash-a", "hash-b"}
    # All unknown.
    assert await known_import_hashes(auth_schema, ["nope-1", "nope-2"]) == set()
    # Mix → only the persisted subset.
    assert await known_import_hashes(auth_schema, ["hash-a", "nope"]) == {"hash-a"}


async def test_link_nonexistent_account_raises_integrity(auth_schema: AsyncSession) -> None:
    # The FK refuses a link to a non-existent account — the service creates no
    # account (AC #176). The violation surfaces at flush (DB-level).
    with pytest.raises(IntegrityError):
        await link(
            auth_schema,
            external_ref="XXXX1234",
            internal_account_id=uuid.uuid4(),
            provider="ofx",
        )


@pytest.mark.usefixtures("_clean_committed_db")
async def test_link_does_not_commit(committed_engine: AsyncEngine) -> None:
    # Flush-only contract (ADR 0015, D5): the service never commits, so an
    # independent session must not see the link once the caller's session closes
    # without committing (rolling back). Gabarit `test_create_does_not_commit`.
    sm = async_sessionmaker(committed_engine, expire_on_commit=False)
    async with sm() as session:
        session.add(
            Household(
                name="Committed Household",
                base_currency="EUR",
                initialized_at=datetime.now(tz=UTC),
            )
        )
        user = User(
            email="owner@example.com",
            password_hash="x" * 60,
            display_name="owner",
            role=UserRole.MEMBER,
        )
        session.add(user)
        await session.flush()
        account = Account(name="Perso", type=AccountType.COURANT, currency="EUR", owner_id=user.id)
        session.add(account)
        await session.flush()
        account_id = account.id
        await session.commit()

    async with sm() as session:
        ref = await link(
            session, external_ref="XXXX1234", internal_account_id=account_id, provider="ofx"
        )
        assert ref.id is not None
        # Deliberately no commit — closing the session rolls back.

    async with sm() as session:
        count = (
            await session.execute(select(func.count()).select_from(BankAccountExternalRef))
        ).scalar_one()
        assert count == 0
