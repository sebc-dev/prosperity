"""Integration tests for `debts.models` (S09.1 `Debt` / `ShareRequest`).

Exercise the persisted behaviour the unit tier and the level-1 snapshot cannot
reach: the `ON DELETE CASCADE`/`RESTRICT`/`SET NULL` FK matrix, the two
defensive CHECKs (`amount_cents > 0`, anti self-debt), the partial unique that
forbids two *active* share requests on the same (tx, débiteur) pair while a
revoked one frees the slot, and the activation of the dormant FK
`transactions.share_request_id → share_requests.id` (`SET NULL`). Pure `flush`
+ rollback isolation (`household_singleton`) — FK/CHECK violations surface at
`flush` because they are DB-level.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Awaitable, Callable
from decimal import Decimal

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.accounts.domain import AccountType
from backend.modules.accounts.models import Account
from backend.modules.auth.models import User
from backend.modules.debts.models import Debt, ShareRequest
from backend.modules.transactions.models import Transaction

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


async def _make_transaction(
    session: AsyncSession, *, account_id: uuid.UUID, created_by: uuid.UUID
) -> uuid.UUID:
    tx = Transaction(
        account_id=account_id,
        date=dt.date(2026, 6, 1),
        state="confirmed",
        created_by=created_by,
    )
    session.add(tx)
    await session.flush()
    return tx.id


async def _make_debt(  # noqa: PLR0913 — keyword-only seed helper
    session: AsyncSession,
    *,
    from_user_id: uuid.UUID,
    to_user_id: uuid.UUID,
    account_id: uuid.UUID,
    source_transaction_id: uuid.UUID,
    amount_cents: int = 5000,
    origin: str = "personal_share_request",
) -> Debt:
    debt = Debt(
        from_user_id=from_user_id,
        to_user_id=to_user_id,
        amount_cents=amount_cents,
        currency="EUR",
        account_id=account_id,
        source_transaction_id=source_transaction_id,
        origin=origin,
    )
    session.add(debt)
    await session.flush()
    return debt


# ---------------------------------------------------------------------------
# Debt (P09.1.1)
# ---------------------------------------------------------------------------


async def test_debt_persists_with_defaults(
    household_singleton: AsyncSession,
    bound_user_factory: Callable[..., Awaitable[User]],
) -> None:
    # Livrable observable: a debt persists end to end; `share_ratio` defaults to
    # 1.0, `created_at` rounds the server_default, `materialization_trace` is
    # NULL (no calc run in the MVP synchronous one-shot insert).
    debtor = await bound_user_factory()
    creditor = await bound_user_factory()
    account_id = await _make_account(household_singleton, creditor.id)
    tx_id = await _make_transaction(
        household_singleton, account_id=account_id, created_by=creditor.id
    )
    debt = await _make_debt(
        household_singleton,
        from_user_id=debtor.id,
        to_user_id=creditor.id,
        account_id=account_id,
        source_transaction_id=tx_id,
    )
    debt_id = debt.id

    household_singleton.expire_all()
    reloaded = (
        await household_singleton.execute(select(Debt).where(Debt.id == debt_id))
    ).scalar_one()
    assert reloaded.amount_cents == 5000
    assert float(reloaded.share_ratio) == 1.0
    assert reloaded.created_at is not None
    assert reloaded.materialization_trace is None
    assert reloaded.origin == "personal_share_request"


async def test_origin_accepts_arbitrary_string(
    household_singleton: AsyncSession,
    bound_user_factory: Callable[..., Awaitable[User]],
) -> None:
    # No DB CHECK on `origin`: the closed set lives at the Pydantic boundary
    # (S09.3). An arbitrary value persists here — behavioural twin of the unit
    # `test_origin_has_no_check`.
    debtor = await bound_user_factory()
    creditor = await bound_user_factory()
    account_id = await _make_account(household_singleton, creditor.id)
    tx_id = await _make_transaction(
        household_singleton, account_id=account_id, created_by=creditor.id
    )
    debt = await _make_debt(
        household_singleton,
        from_user_id=debtor.id,
        to_user_id=creditor.id,
        account_id=account_id,
        source_transaction_id=tx_id,
        origin="some_future_origin_F10",
    )
    assert debt.origin == "some_future_origin_F10"  # no IntegrityError


async def test_self_debt_violates_check(
    household_singleton: AsyncSession,
    bound_user_factory: Callable[..., Awaitable[User]],
) -> None:
    # `ck_debts_no_self_debt`: a user cannot owe themselves (DB twin of the
    # S09.5 property).
    user = await bound_user_factory()
    account_id = await _make_account(household_singleton, user.id)
    tx_id = await _make_transaction(household_singleton, account_id=account_id, created_by=user.id)
    with pytest.raises(IntegrityError):
        await _make_debt(
            household_singleton,
            from_user_id=user.id,
            to_user_id=user.id,
            account_id=account_id,
            source_transaction_id=tx_id,
        )


@pytest.mark.parametrize("amount", [0, -1])
async def test_non_positive_amount_violates_check(
    household_singleton: AsyncSession,
    bound_user_factory: Callable[..., Awaitable[User]],
    amount: int,
) -> None:
    # `ck_debts_amount_positive`: a materialised debt always carries a strictly
    # positive amount (guards against a null/negative projection).
    debtor = await bound_user_factory()
    creditor = await bound_user_factory()
    account_id = await _make_account(household_singleton, creditor.id)
    tx_id = await _make_transaction(
        household_singleton, account_id=account_id, created_by=creditor.id
    )
    with pytest.raises(IntegrityError):
        await _make_debt(
            household_singleton,
            from_user_id=debtor.id,
            to_user_id=creditor.id,
            account_id=account_id,
            source_transaction_id=tx_id,
            amount_cents=amount,
        )


async def test_delete_source_transaction_cascades_debt(
    household_singleton: AsyncSession,
    bound_user_factory: Callable[..., Awaitable[User]],
) -> None:
    # `source_transaction_id` ON DELETE CASCADE: deleting the source tx removes
    # its projected debt.
    debtor = await bound_user_factory()
    creditor = await bound_user_factory()
    account_id = await _make_account(household_singleton, creditor.id)
    tx_id = await _make_transaction(
        household_singleton, account_id=account_id, created_by=creditor.id
    )
    await _make_debt(
        household_singleton,
        from_user_id=debtor.id,
        to_user_id=creditor.id,
        account_id=account_id,
        source_transaction_id=tx_id,
    )

    tx = (
        await household_singleton.execute(select(Transaction).where(Transaction.id == tx_id))
    ).scalar_one()
    await household_singleton.delete(tx)
    await household_singleton.flush()

    count = (
        await household_singleton.execute(
            text("SELECT count(*) FROM debts WHERE source_transaction_id = :id"),
            {"id": tx_id},
        )
    ).scalar_one()
    assert count == 0


async def test_delete_account_referenced_by_debt_is_restricted(
    household_singleton: AsyncSession,
    bound_user_factory: Callable[..., Awaitable[User]],
) -> None:
    # `account_id` ON DELETE RESTRICT: the source account cannot be hard-deleted
    # while a debt projection still references it.
    debtor = await bound_user_factory()
    creditor = await bound_user_factory()
    account_id = await _make_account(household_singleton, creditor.id)
    tx_id = await _make_transaction(
        household_singleton, account_id=account_id, created_by=creditor.id
    )
    await _make_debt(
        household_singleton,
        from_user_id=debtor.id,
        to_user_id=creditor.id,
        account_id=account_id,
        source_transaction_id=tx_id,
    )

    account = (
        await household_singleton.execute(select(Account).where(Account.id == account_id))
    ).scalar_one()
    await household_singleton.delete(account)
    with pytest.raises(IntegrityError):  # ON DELETE RESTRICT
        await household_singleton.flush()


async def test_delete_user_referenced_by_debt_is_restricted(
    household_singleton: AsyncSession,
    bound_user_factory: Callable[..., Awaitable[User]],
) -> None:
    # `from_user_id`/`to_user_id` ON DELETE RESTRICT (F02): a user is disabled,
    # never hard-deleted while a debt references them.
    debtor = await bound_user_factory()
    creditor = await bound_user_factory()
    account_id = await _make_account(household_singleton, creditor.id)
    tx_id = await _make_transaction(
        household_singleton, account_id=account_id, created_by=creditor.id
    )
    await _make_debt(
        household_singleton,
        from_user_id=debtor.id,
        to_user_id=creditor.id,
        account_id=account_id,
        source_transaction_id=tx_id,
    )

    await household_singleton.delete(debtor)
    with pytest.raises(IntegrityError):
        await household_singleton.flush()


# ---------------------------------------------------------------------------
# ShareRequest (P09.1.2)
# ---------------------------------------------------------------------------


async def _make_share_request(
    session: AsyncSession,
    *,
    source_transaction_id: uuid.UUID,
    requested_by: uuid.UUID,
    requested_from: uuid.UUID,
    revoked_at: dt.datetime | None = None,
) -> ShareRequest:
    sr = ShareRequest(
        source_transaction_id=source_transaction_id,
        requested_by=requested_by,
        requested_from=requested_from,
        ratio=Decimal("0.5000"),
        short_label="Courses partagées",
        revoked_at=revoked_at,
    )
    session.add(sr)
    await session.flush()
    return sr


async def test_share_request_persists(
    household_singleton: AsyncSession,
    bound_user_factory: Callable[..., Awaitable[User]],
) -> None:
    owner = await bound_user_factory()
    debtor = await bound_user_factory()
    account_id = await _make_account(household_singleton, owner.id)
    tx_id = await _make_transaction(household_singleton, account_id=account_id, created_by=owner.id)
    sr = await _make_share_request(
        household_singleton,
        source_transaction_id=tx_id,
        requested_by=owner.id,
        requested_from=debtor.id,
    )
    sr_id = sr.id

    household_singleton.expire_all()
    reloaded = (
        await household_singleton.execute(select(ShareRequest).where(ShareRequest.id == sr_id))
    ).scalar_one()
    assert reloaded.created_at is not None
    assert reloaded.revoked_at is None
    assert reloaded.short_label == "Courses partagées"


async def test_self_share_request_violates_check(
    household_singleton: AsyncSession,
    bound_user_factory: Callable[..., Awaitable[User]],
) -> None:
    # `ck_share_requests_no_self`: one cannot share an expense with oneself.
    owner = await bound_user_factory()
    account_id = await _make_account(household_singleton, owner.id)
    tx_id = await _make_transaction(household_singleton, account_id=account_id, created_by=owner.id)
    with pytest.raises(IntegrityError):
        await _make_share_request(
            household_singleton,
            source_transaction_id=tx_id,
            requested_by=owner.id,
            requested_from=owner.id,
        )


async def test_two_active_share_requests_same_pair_violate_unique(
    household_singleton: AsyncSession,
    bound_user_factory: Callable[..., Awaitable[User]],
) -> None:
    # Partial unique `(source_transaction_id, requested_from) WHERE revoked_at
    # IS NULL`: two ACTIVE share requests on the same (tx, débiteur) pair are
    # refused.
    owner = await bound_user_factory()
    debtor = await bound_user_factory()
    account_id = await _make_account(household_singleton, owner.id)
    tx_id = await _make_transaction(household_singleton, account_id=account_id, created_by=owner.id)
    await _make_share_request(
        household_singleton,
        source_transaction_id=tx_id,
        requested_by=owner.id,
        requested_from=debtor.id,
    )
    with pytest.raises(IntegrityError):
        await _make_share_request(
            household_singleton,
            source_transaction_id=tx_id,
            requested_by=owner.id,
            requested_from=debtor.id,
        )


async def test_revoked_share_request_frees_the_slot(
    household_singleton: AsyncSession,
    bound_user_factory: Callable[..., Awaitable[User]],
) -> None:
    # The partial predicate excludes revoked rows: once the first SR is revoked
    # (`revoked_at` set), a NEW active SR on the same pair flushes cleanly.
    owner = await bound_user_factory()
    debtor = await bound_user_factory()
    account_id = await _make_account(household_singleton, owner.id)
    tx_id = await _make_transaction(household_singleton, account_id=account_id, created_by=owner.id)
    await _make_share_request(
        household_singleton,
        source_transaction_id=tx_id,
        requested_by=owner.id,
        requested_from=debtor.id,
        revoked_at=dt.datetime(2026, 6, 2, tzinfo=dt.UTC),
    )
    # Same pair, but the prior one is revoked → no conflict.
    await _make_share_request(
        household_singleton,
        source_transaction_id=tx_id,
        requested_by=owner.id,
        requested_from=debtor.id,
    )  # no IntegrityError


async def test_delete_source_transaction_cascades_share_request(
    household_singleton: AsyncSession,
    bound_user_factory: Callable[..., Awaitable[User]],
) -> None:
    # `source_transaction_id` ON DELETE CASCADE: deleting the source tx removes
    # its share requests too.
    owner = await bound_user_factory()
    debtor = await bound_user_factory()
    account_id = await _make_account(household_singleton, owner.id)
    tx_id = await _make_transaction(household_singleton, account_id=account_id, created_by=owner.id)
    await _make_share_request(
        household_singleton,
        source_transaction_id=tx_id,
        requested_by=owner.id,
        requested_from=debtor.id,
    )

    tx = (
        await household_singleton.execute(select(Transaction).where(Transaction.id == tx_id))
    ).scalar_one()
    await household_singleton.delete(tx)
    await household_singleton.flush()

    count = (
        await household_singleton.execute(
            text("SELECT count(*) FROM share_requests WHERE source_transaction_id = :id"),
            {"id": tx_id},
        )
    ).scalar_one()
    assert count == 0


@pytest.mark.parametrize("role", ["requested_by", "requested_from"])
async def test_delete_user_referenced_by_share_request_is_restricted(
    household_singleton: AsyncSession,
    bound_user_factory: Callable[..., Awaitable[User]],
    role: str,
) -> None:
    # `requested_by`/`requested_from` ON DELETE RESTRICT (F02): a user is
    # disabled, never hard-deleted while a share request references them — on
    # either side of the pair (DB twin of `test_delete_user_referenced_by_debt`).
    # The account/tx are owned by a SEPARATE `owner` so the deleted user is
    # referenced ONLY by the share request — isolating the RESTRICT under test
    # from the (also-RESTRICT) `accounts.owner_id` / `transactions.created_by`.
    owner = await bound_user_factory()
    requester = await bound_user_factory()
    debtor = await bound_user_factory()
    account_id = await _make_account(household_singleton, owner.id)
    tx_id = await _make_transaction(household_singleton, account_id=account_id, created_by=owner.id)
    await _make_share_request(
        household_singleton,
        source_transaction_id=tx_id,
        requested_by=requester.id,
        requested_from=debtor.id,
    )

    target = requester if role == "requested_by" else debtor
    await household_singleton.delete(target)
    with pytest.raises(IntegrityError):  # ON DELETE RESTRICT
        await household_singleton.flush()


# ---------------------------------------------------------------------------
# Dormant FK activation: transactions.share_request_id → share_requests.id
# ---------------------------------------------------------------------------


async def test_delete_share_request_nulls_transaction_handle(
    household_singleton: AsyncSession,
    bound_user_factory: Callable[..., Awaitable[User]],
) -> None:
    # The FK activated by 0014 is `ON DELETE SET NULL`: deleting the SR (not the
    # MVP path — revocation sets `revoked_at` — but the DB rule must hold) resets
    # the tx's edit handle to NULL rather than blocking or cascading the tx.
    owner = await bound_user_factory()
    debtor = await bound_user_factory()
    account_id = await _make_account(household_singleton, owner.id)
    tx_id = await _make_transaction(household_singleton, account_id=account_id, created_by=owner.id)
    sr = await _make_share_request(
        household_singleton,
        source_transaction_id=tx_id,
        requested_by=owner.id,
        requested_from=debtor.id,
    )
    # Point the dormant handle at the SR.
    tx = (
        await household_singleton.execute(select(Transaction).where(Transaction.id == tx_id))
    ).scalar_one()
    tx.share_request_id = sr.id
    await household_singleton.flush()

    await household_singleton.delete(sr)
    await household_singleton.flush()

    household_singleton.expire_all()
    reloaded = (
        await household_singleton.execute(select(Transaction).where(Transaction.id == tx_id))
    ).scalar_one()
    assert reloaded.share_request_id is None  # ON DELETE SET NULL


# ---------------------------------------------------------------------------
# Overflow idempotence partial unique index (S11.3 P11.3.1)
# ---------------------------------------------------------------------------


async def test_overflow_unique_index_exists_partial_on_four_columns(
    household_singleton: AsyncSession,
) -> None:
    # `uq_debts_overflow_active` must be UNIQUE, PARTIAL (predicate on the overflow
    # origin) and cover the four columns in order — this is what backs the
    # `ON CONFLICT (source_transaction_id, from_user_id, to_user_id, origin)
    # ... WHERE origin = 'shared_account_overflow'` upsert (P11.3.2).
    indexdef = (
        await household_singleton.execute(
            text(
                "SELECT indexdef FROM pg_indexes "
                "WHERE schemaname = 'public' AND tablename = 'debts' "
                "AND indexname = 'uq_debts_overflow_active'"
            )
        )
    ).scalar_one()
    assert "CREATE UNIQUE INDEX" in indexdef  # unique
    assert "(source_transaction_id, from_user_id, to_user_id, origin)" in indexdef  # 4 cols, order
    # Partial predicate must be on `origin` specifically (not merely "some WHERE"):
    # this is what guarantees exclusivité d'origine — a `personal_share_request`
    # row is outside the index, so it can never collide with an overflow upsert.
    # Normalise away Postgres' `::text` casts and parens so the assertion pins the
    # SEMANTIC predicate (`origin = literal`) rather than the exact
    # `pg_get_indexdef` text rendering, which can shift across PG versions.
    where_clause = indexdef.split("WHERE", 1)[1]
    normalised = where_clause.replace("::text", "").replace("(", "").replace(")", "").strip()
    assert normalised == "origin = 'shared_account_overflow'"


async def test_two_overflow_debts_same_quad_violate_unique(
    household_singleton: AsyncSession,
    bound_user_factory: Callable[..., Awaitable[User]],
) -> None:
    # Outside `ON CONFLICT`, two overflow debts on the same
    # (source_transaction_id, from_user_id, to_user_id, origin) quad are rejected
    # by the partial unique — the invariant the materializer's upsert relies on.
    debtor = await bound_user_factory()
    creditor = await bound_user_factory()
    account_id = await _make_account(household_singleton, creditor.id)
    tx_id = await _make_transaction(
        household_singleton, account_id=account_id, created_by=creditor.id
    )
    await _make_debt(
        household_singleton,
        from_user_id=debtor.id,
        to_user_id=creditor.id,
        account_id=account_id,
        source_transaction_id=tx_id,
        origin="shared_account_overflow",
    )
    with pytest.raises(IntegrityError):
        await _make_debt(
            household_singleton,
            from_user_id=debtor.id,
            to_user_id=creditor.id,
            account_id=account_id,
            source_transaction_id=tx_id,
            origin="shared_account_overflow",
        )


async def test_overflow_and_share_request_debt_same_pair_coexist(
    household_singleton: AsyncSession,
    bound_user_factory: Callable[..., Awaitable[User]],
) -> None:
    # Exclusivité d'origine (durcissement, review sécurité) : a
    # `shared_account_overflow` debt and a `personal_share_request` debt with the
    # EXACTLY same (source_transaction_id, from_user_id, to_user_id) triple
    # coexist — proving it is the PARTIAL predicate (`WHERE origin = ...`), not a
    # data accident, that keeps the upsert from ever touching a share-request
    # debt. Without the partial `WHERE`, a full unique on the quad would let these
    # collide once `origin` were equal; here they differ in origin and the
    # overflow predicate matches only the overflow row.
    debtor = await bound_user_factory()
    creditor = await bound_user_factory()
    account_id = await _make_account(household_singleton, creditor.id)
    tx_id = await _make_transaction(
        household_singleton, account_id=account_id, created_by=creditor.id
    )
    await _make_debt(
        household_singleton,
        from_user_id=debtor.id,
        to_user_id=creditor.id,
        account_id=account_id,
        source_transaction_id=tx_id,
        origin="shared_account_overflow",
    )
    # Same triple, different origin → accepted (no IntegrityError).
    await _make_debt(
        household_singleton,
        from_user_id=debtor.id,
        to_user_id=creditor.id,
        account_id=account_id,
        source_transaction_id=tx_id,
        origin="personal_share_request",
    )
