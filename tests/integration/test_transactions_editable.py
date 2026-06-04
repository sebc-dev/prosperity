"""Integration tests for `transactions.service.lifecycle.update_editable_fields` (S07.4, P07.4.3).

Drives the post-confirmed editing path against a real Postgres: the allowed
fields (`category_id`, `tags`, `description`, `debt_generation_override`,
`share_request_id`) persist; every frozen field raises `ImmutableFieldViolation`;
an unknown field raises `ValueError`; and the `debt_generation_override` DB CHECK
(migration 0010, D14) is the fail-closed backstop for the `model_copy` path that
bypasses Pydantic.

Rollback-isolated tier (`bound_transaction_factories` + `bound_category_factory`):
a `confirmed` transaction is built by the factory (state set directly, balanced
same-account pair). The no-op-on-draft case proves a frozen field passed to this
function is neither rejected nor written below `confirmed`.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Awaitable, Callable

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from backend.modules.debts.models import ShareRequest
from backend.modules.transactions import domain
from backend.modules.transactions.models import Transaction as TxModel
from backend.modules.transactions.service.lifecycle import update_editable_fields
from backend.shared.money import Money

Factories = tuple[type, type, type, type]
BoundFactories = Callable[[], Awaitable[Factories]]
CategoryMaker = Callable[..., Awaitable[object]]


async def _seed_account(
    session: AsyncSession, bound: BoundFactories
) -> tuple[uuid.UUID, uuid.UUID]:
    user_factory, account_factory, _tx, _split = await bound()

    def _build(_sync: object) -> tuple[uuid.UUID, uuid.UUID]:
        user = user_factory()
        return account_factory(owner_id=user.id).id, user.id

    return await session.run_sync(_build)


async def _seed_tx(
    session: AsyncSession,
    bound: BoundFactories,
    *,
    account_id: uuid.UUID,
    user_id: uuid.UUID,
    state: str,
) -> uuid.UUID:
    """A balanced same-account pair in `state` (factory sets the column directly)."""
    _u, _a, tx_factory, _split = await bound()

    def _build(_sync: object) -> uuid.UUID:
        return tx_factory(account_id=account_id, created_by=user_id, state=state).id

    return await session.run_sync(_build)


# ---------------------------------------------------------------------------
# Accepted + persisted (confirmed)
# ---------------------------------------------------------------------------


async def test_edit_category_id_persists(
    household_singleton: AsyncSession,
    bound_transaction_factories: BoundFactories,
    bound_category_factory: CategoryMaker,
) -> None:
    account_id, user_id = await _seed_account(household_singleton, bound_transaction_factories)
    tx_id = await _seed_tx(
        household_singleton,
        bound_transaction_factories,
        account_id=account_id,
        user_id=user_id,
        state="confirmed",
    )
    cat = (await bound_category_factory()).id  # type: ignore[attr-defined]

    after = await update_editable_fields(household_singleton, tx_id=tx_id, category_id=cat)

    assert after.category_id == cat
    persisted = (
        await household_singleton.execute(select(TxModel.category_id).where(TxModel.id == tx_id))
    ).scalar_one()
    assert persisted == cat


async def test_edit_tags_description_override_share_request_persist(
    household_singleton: AsyncSession, bound_transaction_factories: BoundFactories
) -> None:
    account_id, user_id = await _seed_account(household_singleton, bound_transaction_factories)
    tx_id = await _seed_tx(
        household_singleton,
        bound_transaction_factories,
        account_id=account_id,
        user_id=user_id,
        state="confirmed",
    )
    # S09.1 activated the FK `share_request_id → share_requests.id`, so the
    # handle must point at a REAL share request now (was an arbitrary UUID while
    # the column was dormant). Seed one on this tx (requested_from is a second
    # user — `ck_share_requests_no_self`).
    user_factory, _a, _tx, _split = await bound_transaction_factories()

    def _seed_share(sync_session: Session) -> uuid.UUID:
        debtor = user_factory()
        sr = ShareRequest(
            source_transaction_id=tx_id,
            requested_by=user_id,
            requested_from=debtor.id,
            ratio="0.5000",
            short_label="part",
        )
        sync_session.add(sr)
        sync_session.flush()
        return sr.id

    share = await household_singleton.run_sync(_seed_share)

    after = await update_editable_fields(
        household_singleton,
        tx_id=tx_id,
        tags=("voyage", "2026"),
        description="vacances",
        debt_generation_override="force_full_debt",
        share_request_id=share,
    )

    assert after.tags == ("voyage", "2026")
    assert after.description == "vacances"
    assert after.debt_generation_override == "force_full_debt"
    assert after.share_request_id == share
    row = (
        await household_singleton.execute(
            select(
                TxModel.tags,
                TxModel.description,
                TxModel.debt_generation_override,
                TxModel.share_request_id,
            ).where(TxModel.id == tx_id)
        )
    ).one()
    assert list(row[0]) == ["voyage", "2026"]
    assert row[1] == "vacances"
    assert row[2] == "force_full_debt"
    assert row[3] == share


async def test_edit_can_clear_category_and_tags(
    household_singleton: AsyncSession,
    bound_transaction_factories: BoundFactories,
    bound_category_factory: CategoryMaker,
) -> None:
    # Clearing an editable field to its empty form (`category_id=None`, `tags=()`)
    # is allowed post-confirmed — the checker only compares the editable set by
    # value, it does not forbid going back to empty.
    account_id, user_id = await _seed_account(household_singleton, bound_transaction_factories)
    tx_id = await _seed_tx(
        household_singleton,
        bound_transaction_factories,
        account_id=account_id,
        user_id=user_id,
        state="confirmed",
    )
    cat = (await bound_category_factory()).id  # type: ignore[attr-defined]
    await update_editable_fields(household_singleton, tx_id=tx_id, category_id=cat, tags=("x",))

    after = await update_editable_fields(
        household_singleton, tx_id=tx_id, category_id=None, tags=()
    )

    assert after.category_id is None
    assert after.tags == ()
    row = (
        await household_singleton.execute(
            select(TxModel.category_id, TxModel.tags).where(TxModel.id == tx_id)
        )
    ).one()
    assert row[0] is None
    assert list(row[1]) == []


# ---------------------------------------------------------------------------
# Frozen fields rejected on confirmed
# ---------------------------------------------------------------------------


async def test_edit_split_amount_raises(
    household_singleton: AsyncSession, bound_transaction_factories: BoundFactories
) -> None:
    # Mutating a split (here its amount, via a fresh domain Split) diverges the
    # `splits` field by value → ImmutableFieldViolation("splits").
    account_id, user_id = await _seed_account(household_singleton, bound_transaction_factories)
    tx_id = await _seed_tx(
        household_singleton,
        bound_transaction_factories,
        account_id=account_id,
        user_id=user_id,
        state="confirmed",
    )
    tampered = (domain.Split(account_id=account_id, amount=Money(-9999, "EUR")),)

    with pytest.raises(domain.ImmutableFieldViolation) as exc:
        await update_editable_fields(household_singleton, tx_id=tx_id, splits=tampered)
    assert exc.value.field == "splits"


async def test_edit_frozen_scalar_fields_raise(
    household_singleton: AsyncSession, bound_transaction_factories: BoundFactories
) -> None:
    account_id, user_id = await _seed_account(household_singleton, bound_transaction_factories)

    for field, value in (
        ("account_id", uuid.uuid4()),
        ("date", dt.date(2030, 1, 1)),
        ("payee", "AUTRE"),
        ("created_by", uuid.uuid4()),
        ("id", uuid.uuid4()),
    ):
        tx_id = await _seed_tx(
            household_singleton,
            bound_transaction_factories,
            account_id=account_id,
            user_id=user_id,
            state="confirmed",
        )
        with pytest.raises(domain.ImmutableFieldViolation) as exc:
            await update_editable_fields(household_singleton, tx_id=tx_id, **{field: value})
        assert exc.value.field == field


async def test_unknown_field_raises_value_error(
    household_singleton: AsyncSession, bound_transaction_factories: BoundFactories
) -> None:
    account_id, user_id = await _seed_account(household_singleton, bound_transaction_factories)
    tx_id = await _seed_tx(
        household_singleton,
        bound_transaction_factories,
        account_id=account_id,
        user_id=user_id,
        state="confirmed",
    )

    with pytest.raises(ValueError, match="champs inconnus"):
        await update_editable_fields(household_singleton, tx_id=tx_id, nonexistent_field=1)


# ---------------------------------------------------------------------------
# No-op below confirmed (free editing window)
# ---------------------------------------------------------------------------


async def test_draft_frozen_field_is_silent_noop(
    household_singleton: AsyncSession, bound_transaction_factories: BoundFactories
) -> None:
    # Below `confirmed`, passing a frozen field neither raises (checker no-op) nor
    # writes anything (the field is ∉ EDITABLE_AFTER_CONFIRMED) — assert the value
    # is unchanged so the silence is not mistaken for an applied edit.
    account_id, user_id = await _seed_account(household_singleton, bound_transaction_factories)
    tx_id = await _seed_tx(
        household_singleton,
        bound_transaction_factories,
        account_id=account_id,
        user_id=user_id,
        state="draft",
    )
    before = (
        await household_singleton.execute(select(TxModel.payee).where(TxModel.id == tx_id))
    ).scalar_one()

    await update_editable_fields(household_singleton, tx_id=tx_id, payee="IGNORED")

    after = (
        await household_singleton.execute(select(TxModel.payee).where(TxModel.id == tx_id))
    ).scalar_one()
    assert after == before


async def test_draft_editable_field_is_written(
    household_singleton: AsyncSession,
    bound_transaction_factories: BoundFactories,
    bound_category_factory: CategoryMaker,
) -> None:
    # An editable field is written even below `confirmed` (the checker is a no-op,
    # the write loop targets the editable set regardless of state).
    account_id, user_id = await _seed_account(household_singleton, bound_transaction_factories)
    tx_id = await _seed_tx(
        household_singleton,
        bound_transaction_factories,
        account_id=account_id,
        user_id=user_id,
        state="draft",
    )
    cat = (await bound_category_factory()).id  # type: ignore[attr-defined]

    after = await update_editable_fields(household_singleton, tx_id=tx_id, category_id=cat)

    assert after.category_id == cat


# ---------------------------------------------------------------------------
# debt_generation_override DB CHECK backstop (D14)
# ---------------------------------------------------------------------------


async def test_out_of_enum_override_rejected_by_check(
    household_singleton: AsyncSession, bound_transaction_factories: BoundFactories
) -> None:
    # `model_copy` bypasses the Pydantic Literal, so an out-of-enum value reaches
    # the flush — where the DB CHECK ck_transactions_debt_generation_override
    # rejects it (IntegrityError). This is the fail-closed backstop for S07.5's
    # primary 422 guard.
    account_id, user_id = await _seed_account(household_singleton, bound_transaction_factories)
    tx_id = await _seed_tx(
        household_singleton,
        bound_transaction_factories,
        account_id=account_id,
        user_id=user_id,
        state="confirmed",
    )

    # A SAVEPOINT contains the IntegrityError so it rolls back only the inner
    # flush, leaving the outer test transaction healthy for teardown (gabarit
    # `test_budget_categories_service` begin_nested); without it SQLAlchemy emits
    # a "transaction already deassociated" warning.
    savepoint = await household_singleton.begin_nested()
    with pytest.raises(IntegrityError):
        await update_editable_fields(
            household_singleton, tx_id=tx_id, debt_generation_override="arbitrary"
        )
    await savepoint.rollback()
