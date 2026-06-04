"""Integration tests for `transactions.service.lifecycle` — transitions + events (S07.4, P07.4.2).

Drives `transition_to_planned` / `transition_to_confirmed` / `void` against a
real Postgres: the state machine wired onto the ORM, the zero-sum + expense-
categorisation gates, the `confirmed_at`/`voided_at` stamps, and the
`DomainEvent` emission. The mini-bus contract (S05.4) is exercised end to end —
a spy receives the event in the same transaction, and a subscriber that **raises
rolls the whole transition back** (verified from an independent session on
`committed_engine`, the most important guarantee here).

Tiers (gabarit `test_transactions_lifecycle.py`):

* Rollback-isolated (`bound_transaction_factories` + `bound_category_factory`):
  valid/invalid transitions, the gates, and the in-process event spy.
* Real-commit (`committed_engine` / `_clean_committed_db`): the
  raise-rolls-back proof, checked from a fresh session.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable, Iterator
from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from backend.modules.accounts.domain import AccountType
from backend.modules.accounts.models import Account, Household
from backend.modules.auth.models import User, UserRole
from backend.modules.transactions import domain
from backend.modules.transactions.events import (
    TransactionConfirmedEvent,
    TransactionVoidedEvent,
)
from backend.modules.transactions.models import Split as SplitModel
from backend.modules.transactions.models import Transaction as TxModel
from backend.modules.transactions.service.lifecycle import (
    transition_to_confirmed,
    transition_to_planned,
    void,
)
from backend.shared.events import (
    DomainEvent,
    clear_subscribers,
    subscribe,
    subscribe_async,
)

Factories = tuple[type, type, type, type]
BoundFactories = Callable[[], Awaitable[Factories]]
CategoryMaker = Callable[..., Awaitable[object]]

# A leg: (account_id, amount_cents, category_id).
Leg = tuple[uuid.UUID, int, uuid.UUID | None]


@pytest.fixture(autouse=True)
def _clear_bus() -> Iterator[None]:  # pyright: ignore[reportUnusedFunction]
    """Empty the global mini-bus registry around every test (process-global state)."""
    clear_subscribers()
    yield
    clear_subscribers()


# ---------------------------------------------------------------------------
# Rollback-isolated tier helpers
# ---------------------------------------------------------------------------


async def _seed_account(
    session: AsyncSession, bound: BoundFactories
) -> tuple[uuid.UUID, uuid.UUID]:
    user_factory, account_factory, _tx, _split = await bound()

    def _build(_sync: object) -> tuple[uuid.UUID, uuid.UUID]:
        user = user_factory()
        account = account_factory(owner_id=user.id)
        return account.id, user.id

    return await session.run_sync(_build)


async def _seed_second_account(session: AsyncSession, bound: BoundFactories) -> uuid.UUID:
    user_factory, account_factory, _tx, _split = await bound()

    def _build(_sync: object) -> uuid.UUID:
        return account_factory(owner_id=user_factory().id).id

    return await session.run_sync(_build)


async def _seed_tx(  # noqa: PLR0913 — keyword-only test seed; arity is intentional
    session: AsyncSession,
    bound: BoundFactories,
    *,
    account_id: uuid.UUID,
    user_id: uuid.UUID,
    state: str,
    legs: list[Leg],
    leg_roles: list[str | None] | None = None,
) -> uuid.UUID:
    """Build a transaction in `state` with explicit split legs; returns its id.

    `leg_roles` (optional, parallel to `legs`) FORCES `leg_role` on a leg — used
    to seed a divergent `classification`/NULL leg (which the ORM default would
    otherwise derive to `funding`). Omitted ⇒ each leg's role is derived from its
    `category_id` (S08.5.1 default), the normal case.
    """
    _u, _a, tx_factory, split_factory = await bound()
    roles = leg_roles if leg_roles is not None else [None] * len(legs)

    def _build(_sync: object) -> uuid.UUID:
        tx = tx_factory(account_id=account_id, created_by=user_id, state=state, splits=False)
        for (acc, amount, cat), role in zip(legs, roles, strict=True):
            extra = {"leg_role": role} if role is not None else {}
            split_factory(
                transaction_id=tx.id,
                account_id=acc,
                amount_cents=amount,
                category_id=cat,
                **extra,
            )
        return tx.id

    return await session.run_sync(_build)


# ---------------------------------------------------------------------------
# transition_to_planned
# ---------------------------------------------------------------------------


async def test_planned_from_balanced_draft(
    household_singleton: AsyncSession, bound_transaction_factories: BoundFactories
) -> None:
    account_id, user_id = await _seed_account(household_singleton, bound_transaction_factories)
    tx_id = await _seed_tx(
        household_singleton,
        bound_transaction_factories,
        account_id=account_id,
        user_id=user_id,
        state="draft",
        legs=[(account_id, -1000, None), (account_id, 1000, None)],
    )

    tx = await transition_to_planned(household_singleton, tx_id=tx_id)

    assert tx.state is domain.TransactionState.PLANNED


async def test_planned_rejects_unbalanced(
    household_singleton: AsyncSession, bound_transaction_factories: BoundFactories
) -> None:
    account_id, user_id = await _seed_account(household_singleton, bound_transaction_factories)
    tx_id = await _seed_tx(
        household_singleton,
        bound_transaction_factories,
        account_id=account_id,
        user_id=user_id,
        state="draft",
        legs=[(account_id, -1000, None), (account_id, 700, None)],
    )

    with pytest.raises(domain.UnbalancedTransactionError):
        await transition_to_planned(household_singleton, tx_id=tx_id)


async def test_planned_from_non_draft_is_invalid(
    household_singleton: AsyncSession, bound_transaction_factories: BoundFactories
) -> None:
    account_id, user_id = await _seed_account(household_singleton, bound_transaction_factories)
    tx_id = await _seed_tx(
        household_singleton,
        bound_transaction_factories,
        account_id=account_id,
        user_id=user_id,
        state="confirmed",
        legs=[(account_id, -1000, None), (account_id, 1000, None)],
    )

    with pytest.raises(domain.InvalidStateTransitionError):
        await transition_to_planned(household_singleton, tx_id=tx_id)


# ---------------------------------------------------------------------------
# transition_to_confirmed
# ---------------------------------------------------------------------------


async def test_confirm_categorized_expense(
    household_singleton: AsyncSession,
    bound_transaction_factories: BoundFactories,
    bound_category_factory: CategoryMaker,
) -> None:
    account_id, user_id = await _seed_account(household_singleton, bound_transaction_factories)
    cat = (await bound_category_factory()).id  # type: ignore[attr-defined]
    tx_id = await _seed_tx(
        household_singleton,
        bound_transaction_factories,
        account_id=account_id,
        user_id=user_id,
        state="planned",
        legs=[(account_id, -1000, cat), (account_id, 1000, cat)],
    )

    tx = await transition_to_confirmed(household_singleton, tx_id=tx_id)

    assert tx.state is domain.TransactionState.CONFIRMED
    confirmed_at = (
        await household_singleton.execute(select(TxModel.confirmed_at).where(TxModel.id == tx_id))
    ).scalar_one()
    assert confirmed_at is not None


async def test_confirm_rejects_unbalanced(
    household_singleton: AsyncSession, bound_transaction_factories: BoundFactories
) -> None:
    account_id, user_id = await _seed_account(household_singleton, bound_transaction_factories)
    tx_id = await _seed_tx(
        household_singleton,
        bound_transaction_factories,
        account_id=account_id,
        user_id=user_id,
        state="planned",
        legs=[(account_id, -1000, None), (account_id, 600, None)],
    )

    with pytest.raises(domain.UnbalancedTransactionError):
        await transition_to_confirmed(household_singleton, tx_id=tx_id)


async def test_confirm_rejects_uncategorized_expense(
    household_singleton: AsyncSession, bound_transaction_factories: BoundFactories
) -> None:
    # ADR 0017 : only a `classification` leg requires a category. Canonical form B
    # with the classification leg's category FORCED to NULL → refused. The funding
    # leg (NULL, derived) is exempt — what's rejected is the divergent
    # classification/NULL leg (authoritative DB value, not re-derived).
    account_id, user_id = await _seed_account(household_singleton, bound_transaction_factories)
    tx_id = await _seed_tx(
        household_singleton,
        bound_transaction_factories,
        account_id=account_id,
        user_id=user_id,
        state="planned",
        legs=[(account_id, -1000, None), (account_id, 1000, None)],
        leg_roles=[None, "classification"],  # funding (derived) + classification/NULL (forced)
    )

    with pytest.raises(domain.UncategorizedExpenseError) as exc:
        await transition_to_confirmed(household_singleton, tx_id=tx_id)
    assert exc.value.transaction_id == tx_id


async def test_confirm_rejects_two_funding_legs(
    household_singleton: AsyncSession, bound_transaction_factories: BoundFactories
) -> None:
    # D2/D3 (ADR 0017) : a same-account pair with two NULL-category legs derives
    # two `funding` legs → trips the ≤1-funding invariant (categorisation passes,
    # 0 classification). Pins the confirm-gate through the real service flow.
    account_id, user_id = await _seed_account(household_singleton, bound_transaction_factories)
    tx_id = await _seed_tx(
        household_singleton,
        bound_transaction_factories,
        account_id=account_id,
        user_id=user_id,
        state="planned",
        legs=[(account_id, -1000, None), (account_id, 1000, None)],
    )

    with pytest.raises(domain.MultipleFundingLegsError) as exc:
        await transition_to_confirmed(household_singleton, tx_id=tx_id)
    assert exc.value.transaction_id == tx_id


async def test_confirm_transfer_without_category_ok(
    household_singleton: AsyncSession, bound_transaction_factories: BoundFactories
) -> None:
    # Two distinct accounts → structural transfer → categorisation not required.
    account_id, user_id = await _seed_account(household_singleton, bound_transaction_factories)
    other = await _seed_second_account(household_singleton, bound_transaction_factories)
    tx_id = await _seed_tx(
        household_singleton,
        bound_transaction_factories,
        account_id=account_id,
        user_id=user_id,
        state="planned",
        legs=[(account_id, -1000, None), (other, 1000, None)],
    )

    tx = await transition_to_confirmed(household_singleton, tx_id=tx_id)

    assert tx.state is domain.TransactionState.CONFIRMED


async def test_confirm_directly_from_draft_is_invalid(
    household_singleton: AsyncSession, bound_transaction_factories: BoundFactories
) -> None:
    account_id, user_id = await _seed_account(household_singleton, bound_transaction_factories)
    tx_id = await _seed_tx(
        household_singleton,
        bound_transaction_factories,
        account_id=account_id,
        user_id=user_id,
        state="draft",
        legs=[(account_id, -1000, None), (account_id, 1000, None)],
    )

    with pytest.raises(domain.InvalidStateTransitionError):
        await transition_to_confirmed(household_singleton, tx_id=tx_id)


async def test_reconfirm_is_invalid(
    household_singleton: AsyncSession, bound_transaction_factories: BoundFactories
) -> None:
    # Re-confirming a `confirmed` fails cleanly (a network replay does not double
    # the effect).
    account_id, user_id = await _seed_account(household_singleton, bound_transaction_factories)
    tx_id = await _seed_tx(
        household_singleton,
        bound_transaction_factories,
        account_id=account_id,
        user_id=user_id,
        state="confirmed",
        legs=[(account_id, -1000, None), (account_id, 1000, None)],
    )

    with pytest.raises(domain.InvalidStateTransitionError):
        await transition_to_confirmed(household_singleton, tx_id=tx_id)


# ---------------------------------------------------------------------------
# void
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("state", ["draft", "planned", "confirmed"])
async def test_void_from_non_void_states(
    household_singleton: AsyncSession, bound_transaction_factories: BoundFactories, state: str
) -> None:
    account_id, user_id = await _seed_account(household_singleton, bound_transaction_factories)
    tx_id = await _seed_tx(
        household_singleton,
        bound_transaction_factories,
        account_id=account_id,
        user_id=user_id,
        state=state,
        legs=[(account_id, -1000, None), (account_id, 1000, None)],
    )

    tx = await void(household_singleton, tx_id=tx_id, reason="erreur de saisie")

    assert tx.state is domain.TransactionState.VOID
    voided_at = (
        await household_singleton.execute(select(TxModel.voided_at).where(TxModel.id == tx_id))
    ).scalar_one()
    assert voided_at is not None


async def test_void_is_terminal(
    household_singleton: AsyncSession, bound_transaction_factories: BoundFactories
) -> None:
    account_id, user_id = await _seed_account(household_singleton, bound_transaction_factories)
    tx_id = await _seed_tx(
        household_singleton,
        bound_transaction_factories,
        account_id=account_id,
        user_id=user_id,
        state="void",
        legs=[(account_id, -1000, None), (account_id, 1000, None)],
    )

    with pytest.raises(domain.InvalidStateTransitionError):
        await void(household_singleton, tx_id=tx_id, reason="re-void")


# ---------------------------------------------------------------------------
# Events (in-process mini-bus spy)
# ---------------------------------------------------------------------------


async def test_confirm_emits_event(
    household_singleton: AsyncSession,
    bound_transaction_factories: BoundFactories,
    bound_category_factory: CategoryMaker,
) -> None:
    received: list[TransactionConfirmedEvent] = []
    subscribe(TransactionConfirmedEvent, received.append)
    account_id, user_id = await _seed_account(household_singleton, bound_transaction_factories)
    cat = (await bound_category_factory()).id  # type: ignore[attr-defined]
    tx_id = await _seed_tx(
        household_singleton,
        bound_transaction_factories,
        account_id=account_id,
        user_id=user_id,
        state="planned",
        legs=[(account_id, -1000, cat), (account_id, 1000, cat)],
    )

    await transition_to_confirmed(household_singleton, tx_id=tx_id)

    assert len(received) == 1
    assert received[0].transaction_id == tx_id
    assert received[0].account_id == account_id


async def test_confirm_dispatches_async_handler_in_request_transaction(
    household_singleton: AsyncSession,
    bound_transaction_factories: BoundFactories,
    bound_category_factory: CategoryMaker,
) -> None:
    # An ASYNC subscriber (S08.3 channel) receives `(session, event)` during the
    # confirm and runs INSIDE the request transaction: it reads the just-flushed
    # `confirmed` row through the very session it was handed (proof of same-tx).
    seen: list[tuple[bool, str | None]] = []

    async def _async_handler(session: AsyncSession, event: TransactionConfirmedEvent) -> None:
        state = (
            await session.execute(select(TxModel.state).where(TxModel.id == event.transaction_id))
        ).scalar_one()
        seen.append((session is household_singleton, state))

    subscribe_async(TransactionConfirmedEvent, _async_handler)
    account_id, user_id = await _seed_account(household_singleton, bound_transaction_factories)
    cat = (await bound_category_factory()).id  # type: ignore[attr-defined]
    tx_id = await _seed_tx(
        household_singleton,
        bound_transaction_factories,
        account_id=account_id,
        user_id=user_id,
        state="planned",
        legs=[(account_id, -1000, cat), (account_id, 1000, cat)],
    )

    await transition_to_confirmed(household_singleton, tx_id=tx_id)

    # Same session object, and it observed the flushed `confirmed` state.
    assert seen == [(True, "confirmed")]


@pytest.mark.parametrize("state", ["draft", "planned", "confirmed"])
async def test_void_emits_event_with_reason(
    household_singleton: AsyncSession, bound_transaction_factories: BoundFactories, state: str
) -> None:
    # `void` emits `TransactionVoidedEvent` from ANY non-void source state (the
    # `publish` is unconditional once the transition is accepted).
    received: list[TransactionVoidedEvent] = []
    subscribe(TransactionVoidedEvent, received.append)
    account_id, user_id = await _seed_account(household_singleton, bound_transaction_factories)
    tx_id = await _seed_tx(
        household_singleton,
        bound_transaction_factories,
        account_id=account_id,
        user_id=user_id,
        state=state,
        legs=[(account_id, -1000, None), (account_id, 1000, None)],
    )

    await void(household_singleton, tx_id=tx_id, reason="doublon bancaire")

    assert len(received) == 1
    assert received[0].transaction_id == tx_id
    assert received[0].account_id == account_id
    assert received[0].reason == "doublon bancaire"


async def test_no_event_when_transition_invalid(
    household_singleton: AsyncSession, bound_transaction_factories: BoundFactories
) -> None:
    # An invalid transition raises BEFORE `publish` (which runs after
    # assert_transition / flush) → the spy receives nothing.
    received: list[DomainEvent] = []
    subscribe(TransactionConfirmedEvent, received.append)
    subscribe(TransactionVoidedEvent, received.append)
    account_id, user_id = await _seed_account(household_singleton, bound_transaction_factories)
    tx_id = await _seed_tx(
        household_singleton,
        bound_transaction_factories,
        account_id=account_id,
        user_id=user_id,
        state="draft",
        legs=[(account_id, -1000, None), (account_id, 1000, None)],
    )

    with pytest.raises(domain.InvalidStateTransitionError):
        await transition_to_confirmed(household_singleton, tx_id=tx_id)  # draft → confirmed direct
    assert received == []


# ---------------------------------------------------------------------------
# Real-commit tier — a subscriber that raises rolls the transition back
# ---------------------------------------------------------------------------


async def _seed_committed_transfer(sm: async_sessionmaker[AsyncSession]) -> uuid.UUID:
    """Seed a committed `planned` transfer (2 accounts, balanced, no category)."""
    async with sm() as session:
        session.add(Household(name="Committed", base_currency="EUR"))
        await session.commit()
    async with sm() as session:
        user = User(
            email="tx-tr@example.com",
            password_hash="x" * 60,
            display_name="owner",
            role=UserRole.MEMBER,
        )
        session.add(user)
        await session.flush()
        acc_a = Account(name="A", type=AccountType.COURANT, currency="EUR", owner_id=user.id)
        acc_b = Account(name="B", type=AccountType.COURANT, currency="EUR", owner_id=user.id)
        session.add_all([acc_a, acc_b])
        await session.flush()
        tx = TxModel(
            account_id=acc_a.id,
            created_by=user.id,
            date=datetime.now(UTC).date(),
            state="planned",
        )
        session.add(tx)
        await session.flush()
        session.add_all(
            [
                SplitModel(
                    transaction_id=tx.id, account_id=acc_a.id, amount_cents=-1000, currency="EUR"
                ),
                SplitModel(
                    transaction_id=tx.id, account_id=acc_b.id, amount_cents=1000, currency="EUR"
                ),
            ]
        )
        tx_id = tx.id
        await session.commit()
    return tx_id


@pytest.mark.usefixtures("_clean_committed_db")
async def test_raising_subscriber_rolls_back_transition(committed_engine: AsyncEngine) -> None:
    sm = async_sessionmaker(committed_engine, expire_on_commit=False)
    tx_id = await _seed_committed_transfer(sm)

    def _boom(_event: TransactionConfirmedEvent) -> None:
        raise RuntimeError("subscriber refused the transaction")

    subscribe(TransactionConfirmedEvent, _boom)

    async with sm() as session:
        with pytest.raises(RuntimeError, match="refused"):
            await transition_to_confirmed(session, tx_id=tx_id)
        await session.rollback()

    # From a fresh session: the state is still `planned` (the flushed change to
    # `confirmed` was rolled back when the subscriber raised — same transaction).
    async with sm() as session:
        state = (
            await session.execute(select(TxModel.state).where(TxModel.id == tx_id))
        ).scalar_one()
        assert state == "planned"


@pytest.mark.usefixtures("_clean_committed_db")
async def test_raising_async_subscriber_rolls_back_transition(
    committed_engine: AsyncEngine,
) -> None:
    # Same guarantee for the ASYNC channel (S08.3): a raising async handler
    # propagates through `dispatch` and rolls the confirm back, proven from a
    # fresh session. This is the availability arbitrage of the threshold detector
    # on the critical path (#127 D13) — exercised end to end.
    sm = async_sessionmaker(committed_engine, expire_on_commit=False)
    tx_id = await _seed_committed_transfer(sm)

    async def _boom(_session: AsyncSession, _event: TransactionConfirmedEvent) -> None:
        raise RuntimeError("async subscriber refused the transaction")

    subscribe_async(TransactionConfirmedEvent, _boom)

    async with sm() as session:
        with pytest.raises(RuntimeError, match="refused"):
            await transition_to_confirmed(session, tx_id=tx_id)
        await session.rollback()

    async with sm() as session:
        state = (
            await session.execute(select(TxModel.state).where(TxModel.id == tx_id))
        ).scalar_one()
        assert state == "planned"
