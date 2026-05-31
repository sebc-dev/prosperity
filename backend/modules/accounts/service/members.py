"""Member-management service for shared accounts (S05.4).

`add_member` / `remove_member` / `update_share_ratio` mutate a shared account's
roster after creation. Authorisation is **membership** of the account — never
RBAC, never `_accessible` (which also admits the owner of a *personal* account).
Any non-member (an admin included), the owner of a personal account, an unknown
id, or an archived account is an indistinguishable `None` → uniform 404 at the
route (D5 non-disclosure, consistent with S05.3).

🔒 **Order invariant (normative, D5).** Each mutation evaluates, in order:

  1. `_member_account(...)` → `None` ⇒ **return `None` (→ 404) immediately**,
     before any validation or write;
  2. (PATCH/DELETE) the `target_user_id` must be a current member, else
     **return `None` (→ 404)** — still before validation;
  3. only then `AccountValidator.validate_member_set(roster)` (→ 422);
  4. cross-check the roster shape against the verb (→ `OwnershipShapeError`/422);
  5. apply the writes, then `flush`.

A non-member must never reach step 3: a non-member posting an invalid roster gets
**404, not 422** (otherwise the 422 would betray the account's existence).

The client supplies the **complete** re-balanced roster (total re-balance, D3):
the service validates it but never invents a distribution. Flush-only — `get_db`
owns the commit boundary (ADR 0015); the commit-inside-service derogation does
**not** apply (adding/editing a member is not a security-critical effect the
client must be unable to undo).

Internal to the accounts module; cross-module callers go through
`backend.modules.accounts.public`.
"""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.accounts.domain import (
    AccountValidator,
    MemberShare,
    OwnershipShapeError,
)
from backend.modules.accounts.models import Account, AccountMember


async def _member_account(
    session: AsyncSession, *, account_id: UUID, user_id: UUID
) -> Account | None:
    """The live shared `Account` if `user_id` is a member of it, else `None`.

    Membership = a row in `account_members(account_id, user_id)` with the
    account not archived. A personal account (owner, no members) or an unknown
    id yields `None` → a uniform 404 (D5). Distinct from `_accessible`, which
    also admits the owner.
    """
    stmt = select(Account).where(
        Account.id == account_id,
        Account.archived_at.is_(None),
        Account.id.in_(select(AccountMember.account_id).where(AccountMember.user_id == user_id)),
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def list_members(session: AsyncSession, account_id: UUID) -> list[AccountMember]:
    """The `AccountMember` rows of `account_id` (empty for a personal account).

    A plain `SELECT` (D7) — `Account` maps no relationship, so this avoids any
    async lazy-load at serialisation. Ordered by `joined_at` for a stable view.
    """
    stmt = (
        select(AccountMember)
        .where(AccountMember.account_id == account_id)
        .order_by(AccountMember.joined_at, AccountMember.user_id)
    )
    return list((await session.execute(stmt)).scalars().all())


async def _apply_roster(
    session: AsyncSession,
    *,
    account_id: UUID,
    current: Sequence[AccountMember],
    roster: Sequence[MemberShare],
) -> list[AccountMember]:
    """Reconcile the persisted membership to `roster` (add / update / delete).

    `roster` is already validated (Σ=1, ≥2, positive, no duplicate) and its
    shape cross-checked against the verb by the caller. Members absent from the
    roster are deleted, new ones inserted, and the rest updated to their roster
    ratio. Flushes, then reloads the fresh roster.
    """
    roster_by_user = {ms.user_id: ms for ms in roster}
    current_by_user = {m.user_id: m for m in current}

    for member in current:
        target = roster_by_user.get(member.user_id)
        if target is None:
            await session.delete(member)
        elif member.default_share_ratio != target.ratio:
            member.default_share_ratio = target.ratio

    session.add_all(
        AccountMember(account_id=account_id, user_id=ms.user_id, default_share_ratio=ms.ratio)
        for ms in roster
        if ms.user_id not in current_by_user
    )

    await session.flush()
    return await list_members(session, account_id)


async def add_member(
    session: AsyncSession,
    *,
    account_id: UUID,
    actor_user_id: UUID,
    roster: Sequence[MemberShare],
) -> tuple[Account, list[AccountMember]] | None:
    """Add exactly one member via a complete re-balanced roster.

    `None` if `actor_user_id` is not a member (→ 404), checked first. Otherwise
    validates `roster`, then requires it to add **exactly one** member and remove
    none (else `OwnershipShapeError`/422 — POST is not a removal channel), then
    inserts the newcomer and re-balances the rest. Flush-only.
    """
    account = await _member_account(session, account_id=account_id, user_id=actor_user_id)
    if account is None:
        return None

    current = await list_members(session, account_id)
    AccountValidator.validate_member_set(roster)

    current_users = {m.user_id for m in current}
    roster_users = {ms.user_id for ms in roster}
    added = roster_users - current_users
    removed = current_users - roster_users
    if len(added) != 1 or removed:
        raise OwnershipShapeError("POST /members must add exactly one member and remove none")

    members = await _apply_roster(session, account_id=account_id, current=current, roster=roster)
    return account, members


async def update_share_ratio(
    session: AsyncSession,
    *,
    account_id: UUID,
    actor_user_id: UUID,
    target_user_id: UUID,
    roster: Sequence[MemberShare],
) -> tuple[Account, list[AccountMember]] | None:
    """Edit `target_user_id`'s quote-part via a complete roster (membership fixed).

    `None` if the actor is not a member, or if `target_user_id` is not a current
    member (→ 404), both checked before validation. Otherwise validates `roster`
    and requires it to leave the membership unchanged (`set(roster) ==
    set(current)`, else `OwnershipShapeError`/422), then re-balances. Flush-only.
    """
    account = await _member_account(session, account_id=account_id, user_id=actor_user_id)
    if account is None:
        return None

    current = await list_members(session, account_id)
    current_users = {m.user_id for m in current}
    if target_user_id not in current_users:
        return None

    AccountValidator.validate_member_set(roster)

    if {ms.user_id for ms in roster} != current_users:
        raise OwnershipShapeError("PATCH /members/{user_id} must not change the membership")

    members = await _apply_roster(session, account_id=account_id, current=current, roster=roster)
    return account, members


async def remove_member(
    session: AsyncSession,
    *,
    account_id: UUID,
    actor_user_id: UUID,
    target_user_id: UUID,
    roster: Sequence[MemberShare],
) -> tuple[Account, list[AccountMember]] | None:
    """Remove `target_user_id`, the remaining members re-balanced by `roster`.

    `None` if the actor is not a member, or if `target_user_id` is not a current
    member (→ 404), both before validation. The roster must be exactly
    `current \\ {target}` (else `OwnershipShapeError`/422 — DELETE is not a
    channel for arbitrary membership edits); `validate_member_set` enforces **≥ 2
    remaining** (→ `TooFewMembersError`/422 when removing the second-to-last) and
    Σ=1. Flush-only.
    """
    account = await _member_account(session, account_id=account_id, user_id=actor_user_id)
    if account is None:
        return None

    current = await list_members(session, account_id)
    current_users = {m.user_id for m in current}
    if target_user_id not in current_users:
        return None

    AccountValidator.validate_member_set(roster)

    if {ms.user_id for ms in roster} != current_users - {target_user_id}:
        raise OwnershipShapeError("DELETE /members/{user_id} must drop exactly the target member")

    members = await _apply_roster(session, account_id=account_id, current=current, roster=roster)
    return account, members
