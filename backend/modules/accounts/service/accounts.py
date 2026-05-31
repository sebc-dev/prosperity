"""Account-creation service (S05.2).

`create_personal` / `create_shared` are the functional core the routes
(S05.3) and properties (S05.5) build on. Each reads the household base
currency via `get_household` (intra-module), runs the pure `AccountValidator`
**before any write**, then INSERTs the `Account` (+ the `AccountMember`s) in a
single transaction and **flushes — never commits**: `get_db` owns the
transaction boundary (ADR 0015).

This is an ordinary, transaction-agnostic business service — *not* a
security-critical side effect: ADR 0015's commit-inside-service derogation
deliberately does **not** apply here (the criterion "the client must not be
able to undo the side effect by triggering an exception" is not met). The
boundary stays with `get_db`: commit on success, rollback on exception.

Internal to the accounts module — cross-module callers go through
`backend.modules.accounts.public` (no entry added in S05.2: the only consumer
is the intra-module S05.3 route).
"""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.accounts.domain import AccountType, AccountValidator, MemberShare
from backend.modules.accounts.models import Account, AccountMember
from backend.modules.accounts.service.household import get_household


async def create_personal(
    session: AsyncSession,
    *,
    owner_id: UUID,
    name: str,
    type: AccountType,
    currency: str,
) -> Account:
    """Create a personal account (single owner, no members), atomically.

    Reads `household.base_currency`, validates the creation against the pure
    `AccountValidator` (currency lock + ownership shape), then INSERTs one
    `Account` with `owner_id` set. Flushes to surface the PK; does **not**
    commit (the request's `get_db` owns the boundary, ADR 0015).
    """
    household = await get_household(session)
    AccountValidator.validate(
        currency=currency,
        household_base_currency=household.base_currency,
        owner_id=owner_id,
        members=(),
    )
    account = Account(
        household_id=household.id,
        name=name,
        type=type,
        currency=currency,
        owner_id=owner_id,
    )
    session.add(account)
    await session.flush()  # surface PK here; no commit (get_db owns it, ADR 0015)
    return account


async def create_shared(
    session: AsyncSession,
    *,
    members: Sequence[MemberShare],
    name: str,
    type: AccountType,
    currency: str,
) -> Account:
    """Create a shared account (no owner, ≥ 2 members), atomically.

    Reads `household.base_currency`, validates the creation (currency lock +
    ownership shape + Σ ratios == 1.0000) **before** any write, then INSERTs
    one `Account` (owner NULL) and its `AccountMember` rows. The two flushes
    run in the *same* transaction: the first assigns `account.id` for the
    members' FK; if a member INSERT fails, the transaction is poisoned and
    `get_db` rolls back — nothing is persisted. No commit here (ADR 0015).
    """
    household = await get_household(session)
    AccountValidator.validate(
        currency=currency,
        household_base_currency=household.base_currency,
        owner_id=None,
        members=members,
    )
    account = Account(
        household_id=household.id,
        name=name,
        type=type,
        currency=currency,
        owner_id=None,
    )
    session.add(account)
    await session.flush()  # assign account.id for the members' FK (same transaction)
    session.add_all(
        AccountMember(account_id=account.id, user_id=m.user_id, default_share_ratio=m.ratio)
        for m in members
    )
    await session.flush()
    return account
