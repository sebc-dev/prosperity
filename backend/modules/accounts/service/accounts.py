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
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import ColumnElement, or_, select
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


# --- Resource-scoped access + reads/mutations (S05.3) -----------------------
#
# F03 watertightness is enforced here, by resource — NOT by RBAC at the route
# (D2). The admin is deliberately NOT exempt: `_accessible` is the single
# predicate every read/mutation funnels through, so list and detail can never
# diverge on what a given user may see (D5). It always excludes archived rows,
# so a soft-deleted account is invisible to everyone (the soft-delete oracle
# stays a uniform 404, D4/D7).


def _accessible(user_id: UUID) -> tuple[ColumnElement[bool], ColumnElement[bool]]:
    """WHERE fragments for "visible to `user_id`": owned OR member, AND live.

    Returned as a tuple so callers splat it into `.where(*_accessible(uid))`
    alongside any per-call predicate (e.g. `Account.id == account_id`). The
    membership arm uses a correlated `IN (SELECT …)` rather than a JOIN so the
    personal-ownership arm needs no DISTINCT and the row shape stays `Account`.
    """
    return (
        Account.archived_at.is_(None),
        or_(
            Account.owner_id == user_id,
            Account.id.in_(
                select(AccountMember.account_id).where(AccountMember.user_id == user_id)
            ),
        ),
    )


async def list_accessible(session: AsyncSession, *, user_id: UUID) -> Sequence[Account]:
    """Accounts visible to `user_id` (F03 — no admin exemption), newest first.

    Owned personal accounts ∪ shared accounts where the user is a member,
    archived excluded. A user with no account gets an empty sequence.
    """
    stmt = select(Account).where(*_accessible(user_id)).order_by(Account.created_at.desc())
    return (await session.execute(stmt)).scalars().all()


async def get_accessible(
    session: AsyncSession, *, account_id: UUID, user_id: UUID
) -> Account | None:
    """The account if `user_id` may access it (and it is live), else `None`.

    `None` collapses three indistinguishable cases at the route — unknown id,
    inaccessible, archived — into one uniform 404 (D4 non-disclosure).
    """
    stmt = select(Account).where(Account.id == account_id, *_accessible(user_id))
    return (await session.execute(stmt)).scalar_one_or_none()


async def account_is_accessible(session: AsyncSession, *, account_id: UUID, user_id: UUID) -> bool:
    """`True` iff `user_id` may access `account_id` (owner ∪ live member).

    Collapses the three indistinguishable cases (unknown / inaccessible /
    archived) into a single `False` — the S07.5 route boundary turns it into a
    uniform 404 (non-disclosure, F03). Selects only `Account.id`, never the ORM
    row: a cross-module caller (transactions) has no business handling an
    `accounts` row, only the boolean verdict (D1). The admin is NOT exempt
    (`_accessible` is role-blind).
    """
    stmt = select(Account.id).where(Account.id == account_id, *_accessible(user_id))
    return (await session.execute(stmt)).scalar_one_or_none() is not None


async def accessible_account_ids(session: AsyncSession, *, user_id: UUID) -> set[UUID]:
    """Ids of the accounts visible to `user_id` (owned ∪ shared-member, live).

    Selects ONLY `Account.id` (not full ORM rows): that is exactly what the
    S07.5 list-route filter consumes (`Transaction.account_id IN (...)`) and what
    the create/list boundaries cross-check split `account_id`s against (D1/D5).
    Empty set for a user with no account; archived excluded (`_accessible`).
    """
    stmt = select(Account.id).where(*_accessible(user_id))
    return set((await session.execute(stmt)).scalars().all())


# --- Membership queries for budget consumption (S08.2) ----------------------
#
# Two id-only helpers the budget module's consumption service consumes through
# `accounts.public` to bound which splits a budget counts (D7). `accounts` sits
# *below* `budget` in the directional graph (contract 1), so the `budget →
# accounts.public` import is legitimate — unlike `transactions`, a peer module,
# whose tables budget reads via SQLAlchemy Core. Both select ONLY `Account.id`
# (a cross-module caller has no business handling an `accounts` ORM row) and
# exclude archived accounts (a dead account carries no live activity).


async def owned_personal_account_ids(session: AsyncSession, *, owner_id: UUID) -> set[UUID]:
    """Ids des comptes **personnels** (owner défini) appartenant à `owner_id`, vivants.

    Personnel ⇔ `owner_id IS NOT NULL` (invariant XOR S05.2). Comptes archivés
    exclus. Consommé par les budgets `personal` (S08.2) : borne les splits
    comptés aux comptes du seul contributeur (l'owner).
    """
    stmt = select(Account.id).where(Account.owner_id == owner_id, Account.archived_at.is_(None))
    return set((await session.execute(stmt)).scalars().all())


async def shared_account_ids_with_members_subset(
    session: AsyncSession, *, member_ids: set[UUID]
) -> set[UUID]:
    """Ids des comptes **communs** (owner NULL) dont **tous** les members ∈ `member_ids`, vivants.

    Un compte commun compte pour un budget `shared` ssi *chacun* de ses members
    est contributeur du budget (D7 : sous-ensemble, pas égalité stricte) — un
    compte {A,B,C} ne pollue pas un budget contribué par {A,B} seulement. Vide
    si `member_ids` est vide. Comptes archivés exclus.

    Un compte commun **sans aucun member** (état orphelin) est exclu : la clause
    `notin_` l'inclurait sinon par vacuité (aucun member « étranger »), et
    l'invariant `shared ⇒ ≥2 members` n'est garanti qu'au service (S05.2), pas
    par un CHECK DB — on ne s'y fie donc pas ici (fail-closed, D7).
    """
    if not member_ids:
        return set()
    has_member = select(AccountMember.account_id)
    # Comptes communs vivants SANS aucun member hors `member_ids` : on exclut
    # tout compte qui possède au moins un membre « étranger » à l'ensemble.
    offending = select(AccountMember.account_id).where(AccountMember.user_id.notin_(member_ids))
    stmt = select(Account.id).where(
        Account.owner_id.is_(None),
        Account.archived_at.is_(None),
        Account.id.in_(has_member),
        Account.id.notin_(offending),
    )
    return set((await session.execute(stmt)).scalars().all())


async def shared_account_member_ids(session: AsyncSession) -> set[UUID]:
    """Ids des users membres d'un compte **commun** (owner NULL) vivant (S08.4).

    Union des `account_members.user_id` des comptes communs non archivés.
    Consommé par la validation des contributeurs d'un budget `shared` (chaque
    contributeur doit être membre d'un compte commun, Note implémenteur #128).
    Sélectionne uniquement `user_id` (jamais une ligne ORM, gabarit D1).

    NB prédicat : sémantique **« membre d'au moins un compte commun »**,
    distincte de `shared_account_ids_with_members_subset` (« comptes dont *tous*
    les members ⊆ contributeurs ») utilisé par le filtre de consommation. La
    divergence est assumée (D4) et verrouillée par un test d'invariant croisé.
    """
    stmt = (
        select(AccountMember.user_id)
        .join(Account, Account.id == AccountMember.account_id)
        .where(Account.owner_id.is_(None), Account.archived_at.is_(None))
    )
    return set((await session.execute(stmt)).scalars().all())


# --- Members + quote-parts for overflow materialisation (S11.3) --------------


async def shared_account_members_with_ratios(
    session: AsyncSession, *, account_id: UUID
) -> list[tuple[UUID, Decimal]] | None:
    """Members `(user_id, default_share_ratio)` of the LIVE shared account `account_id`.

    `None` when `account_id` is NOT a live shared account (`owner_id` non-NULL,
    archived, or unknown) → the overflow materializer (S11.3) treats it as a no-op
    (a personal/archived account never generates an implicit debt, CONTEXT.md
    §Origine d'une dette). Returns tuples (never an ORM row): `default_share_ratio`
    is the quote-part that becomes a debt's default `share_ratio` (CONTEXT.md
    §Quote-part). `debts` sits *above* `accounts` in the directional graph
    (contract 1), so this is consumed via `accounts.public` — the legitimate arc.
    """
    is_common = (
        await session.execute(
            select(Account.id).where(
                Account.id == account_id,
                Account.owner_id.is_(None),
                Account.archived_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if is_common is None:
        return None
    rows = await session.execute(
        select(AccountMember.user_id, AccountMember.default_share_ratio).where(
            AccountMember.account_id == account_id
        )
    )
    return [(uid, ratio) for uid, ratio in rows.all()]


async def rename(
    session: AsyncSession, *, account_id: UUID, user_id: UUID, name: str
) -> Account | None:
    """Rename (name only) an accessible account; `None` if not accessible.

    `currency`/`type` are never touched here (frozen at creation, D6).
    Flush-only — `get_db` owns the commit boundary (ADR 0015).
    """
    account = await get_accessible(session, account_id=account_id, user_id=user_id)
    if account is None:
        return None
    account.name = name
    await session.flush()
    return account


async def archive(session: AsyncSession, *, account_id: UUID, user_id: UUID) -> bool:
    """Soft-delete an accessible account (set `archived_at`); never a hard delete.

    Returns `True` on success, `False` if the account is not accessible (→ 404).
    Because `_accessible` already excludes archived rows, a second archive of
    the same account finds nothing → `False` → 404 (idempotent in the sense of
    "no corruption / row preserved", not a 204-replay, D7/C-SEC-4). Flush-only
    (ADR 0015).
    """
    account = await get_accessible(session, account_id=account_id, user_id=user_id)
    if account is None:
        return False
    account.archived_at = datetime.now(UTC)
    await session.flush()
    return True
