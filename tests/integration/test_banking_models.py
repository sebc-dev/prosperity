"""Integration tests for `banking.models` (S12.1, P12.1.1).

Exercise the persisted behaviour the unit tier and the level-1 snapshot cannot
reach: the **DB-enforced** composite UNIQUE `(external_ref, provider)`, the
coexistence of the same `external_ref` under two providers, and the
`ON DELETE RESTRICT` FK to `accounts`. Pure `flush` + rollback isolation
(`auth_schema`/`household_singleton`) — constraint violations surface at `flush`
because they are DB-level. Gabarit `test_transactions_models.py`.

These prove invariant AC #176 n°1 (double `(external_ref, provider)` rejected)
holds at the DATABASE layer, independently of the service-level pre-check (D6)
— it must not rest on application code alone.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.accounts.domain import AccountType
from backend.modules.accounts.models import Account
from backend.modules.auth.models import User
from backend.modules.banking.models import BankAccountExternalRef

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


async def test_duplicate_external_ref_provider_violates_unique(
    auth_schema: AsyncSession,
    bound_user_factory: Callable[..., Awaitable[User]],
) -> None:
    user = await bound_user_factory()
    account_id = await _make_account(auth_schema, user.id)
    auth_schema.add(
        BankAccountExternalRef(
            external_ref="XXXX1234",
            internal_account_id=account_id,
            provider="ofx",
        )
    )
    await auth_schema.flush()

    # Same `(external_ref, provider)` → composite UNIQUE rejects at flush.
    auth_schema.add(
        BankAccountExternalRef(
            external_ref="XXXX1234",
            internal_account_id=account_id,
            provider="ofx",
        )
    )
    with pytest.raises(IntegrityError):
        await auth_schema.flush()


async def test_same_external_ref_two_providers_coexist(
    auth_schema: AsyncSession,
    bound_user_factory: Callable[..., Awaitable[User]],
) -> None:
    # Uniqueness is COMPOSITE, never on `external_ref` alone: the same ref under
    # two distinct providers must coexist (AC #176).
    user = await bound_user_factory()
    account_id = await _make_account(auth_schema, user.id)
    auth_schema.add_all(
        [
            BankAccountExternalRef(
                external_ref="XXXX1234",
                internal_account_id=account_id,
                provider="ofx",
            ),
            BankAccountExternalRef(
                external_ref="XXXX1234",
                internal_account_id=account_id,
                provider="enable_banking",
            ),
        ]
    )
    await auth_schema.flush()

    count = (
        await auth_schema.execute(
            select(BankAccountExternalRef).where(BankAccountExternalRef.external_ref == "XXXX1234")
        )
    ).all()
    assert len(count) == 2


async def test_delete_linked_account_raises_restrict(
    auth_schema: AsyncSession,
    bound_user_factory: Callable[..., Awaitable[User]],
) -> None:
    # `internal_account_id` is `ON DELETE RESTRICT` (F02 — an account is
    # archived, never hard-deleted): deleting a linked account is refused DB-side.
    user = await bound_user_factory()
    account_id = await _make_account(auth_schema, user.id)
    auth_schema.add(
        BankAccountExternalRef(
            external_ref="XXXX1234",
            internal_account_id=account_id,
            provider="ofx",
        )
    )
    await auth_schema.flush()

    account = (
        await auth_schema.execute(select(Account).where(Account.id == account_id))
    ).scalar_one()
    await auth_schema.delete(account)
    with pytest.raises(IntegrityError):
        await auth_schema.flush()
