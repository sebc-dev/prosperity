"""Intégration — matérialisation synchrone de l'overflow F10 via le CHEMIN SYNC (S13.5).

Verrou de régression (étape 6, ADR 0014 ; read-after-write fort, ADR 0002) : la
projection `Debt` overflow (`origin='shared_account_overflow'`) doit être visible
DANS LA MÊME transaction qu'un write passé par le write upload handler. Le mécanisme
réel n'est PAS un appel manuel `materialize_overflow_for_tx` (fonction inexistante,
roadmap corrigé, D2) mais le MINI-BUS : `transition_to_confirmed`/`void` appellent
`dispatch(session, event)`, et les abonnés (`materialize_overflow`/`remove_overflow_on_void`)
tournent IN-TRANSACTION. Cette suite prouve que les sous-handlers `transactions`
(S13.4) s'appuient bien sur ce `dispatch` — un handler qui le court-circuiterait
casserait au moins un test ici (AC #5).

Tous les ACTES passent par `process_batch` (le chemin sync, jamais l'appel service
direct) ; le SEED ne sert qu'à poser l'état (forme B ADR 0017, ids connus). Le câblage
du bus est fourni par la fixture autouse `conftest.py::_wire_sync_subscribers` (gabarit
`test_overflow_materializer.py::_wire_overflow`) — sans elle, `dispatch` serait un no-op
et les tests seraient des FALSE-GREEN.

L'arithmétique (`{bob: 2500}`) reprend `test_default_overflow_proportional` (E11) :
M=100€ (`amount=10000`), budget=50€ (`budget_amount=5000`), ratio 50/50 → base 50€ →
Bob doit 25€ à Alice (payeur = `tx.created_by`, ne se doit jamais rien à lui-même).

L'authz cross-account/foyer du chemin sync est verrouillée à l'ÉTAPE 1 du dispatcher
(`PERMISSION_CHECKS`) et testée par `test_sync_dispatcher_auth.py` — ici l'acteur
(Alice, membre actif) est supposé autorisé.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import Session

from backend.modules.accounts.models import AccountMember, Household
from backend.modules.auth.models import User
from backend.modules.budget.models import Budget, BudgetContributor
from backend.modules.debts.models import Debt
from backend.modules.sync.public import BatchUpload, Mutation, WriteResult
from backend.modules.sync.service.dispatcher import process_batch
from tests.factories.sqlalchemy import (
    AccountFactory,
    CategoryFactory,
    SplitFactory,
    TransactionFactory,
    UserFactory,
)

_OVERFLOW = "shared_account_overflow"
_PERIOD_START = dt.date(2026, 6, 1)
_TX_DATE = dt.date(2026, 6, 15)  # inside the monthly budget window [01, next-01)


@dataclass
class _Seeded:
    alice_id: uuid.UUID  # payer / creditor (tx.created_by)
    bob_id: uuid.UUID  # other member / debtor
    account_id: uuid.UUID
    category_id: uuid.UUID
    tx_id: uuid.UUID


def _mut(table: str, op: str, payload: Mapping[str, object]) -> Mutation:
    return Mutation(client_request_id=uuid.uuid4(), table=table, op=op, payload=dict(payload))  # type: ignore[arg-type]


async def _run(session: AsyncSession, user: User, mutation: Mutation) -> WriteResult:
    [result] = await process_batch(session, user, BatchUpload(mutations=[mutation]))
    return result


def _seed_overflow_scenario(
    s: Session,
    *,
    amount: int,
    budget_amount: int,
    with_legs: bool = True,
    state: str = "planned",
) -> _Seeded:
    """Seed (run_sync, état SEULEMENT) un compte commun Alice+Bob (50/50), une catégorie,
    un budget mensuel `shared` couvert par les deux, et une tx forme B sur ce budget.

    `with_legs=False` (+ `state="draft"`) laisse la tx SANS jambes pour le cas multi-mutations
    où l'acte ajoute les `splits` via `process_batch`. Les factories sont liées à `s` ici
    (pas via le fixture `bound_*`) pour rester agnostique du moteur (rollback OU commit réel).
    """
    for factory in (UserFactory, AccountFactory, CategoryFactory, TransactionFactory, SplitFactory):
        factory._meta.sqlalchemy_session = s  # type: ignore[attr-defined]

    alice = UserFactory(email="alice-overflow@example.com")
    bob = UserFactory(email="bob-overflow@example.com")
    account = AccountFactory(owner_id=None, name="Commun")  # shared → owner NULL
    s.add_all(
        [
            AccountMember(
                account_id=account.id, user_id=alice.id, default_share_ratio=Decimal("0.5")
            ),
            AccountMember(
                account_id=account.id, user_id=bob.id, default_share_ratio=Decimal("0.5")
            ),
        ]
    )
    s.flush()

    category = CategoryFactory(name="Courses")
    budget = Budget(
        category_id=category.id,
        period_kind="monthly",
        period_start=_PERIOD_START,
        amount_cents=budget_amount,
        currency="EUR",
        scope="shared",
        created_by=alice.id,
    )
    s.add(budget)
    s.flush()
    s.add_all(
        [
            BudgetContributor(budget_id=budget.id, user_id=alice.id),
            BudgetContributor(budget_id=budget.id, user_id=bob.id),
        ]
    )
    s.flush()

    tx = TransactionFactory(
        account_id=account.id, created_by=alice.id, state=state, date=_TX_DATE, splits=False
    )
    if with_legs:
        SplitFactory(  # funding leg: category NULL, -M
            transaction_id=tx.id, account_id=account.id, amount_cents=-amount, currency="EUR"
        )
        SplitFactory(  # classification leg: category set, +M (consumes the budget)
            transaction_id=tx.id,
            account_id=account.id,
            amount_cents=amount,
            currency="EUR",
            category_id=category.id,
        )
    return _Seeded(alice.id, bob.id, account.id, category.id, tx.id)


async def _get_user(session: AsyncSession, user_id: uuid.UUID) -> User:
    user = await session.get(User, user_id)
    assert user is not None
    return user


async def _overflow_debts(session: AsyncSession, tx_id: uuid.UUID) -> list[Debt]:
    rows = await session.execute(
        select(Debt)
        .where(Debt.source_transaction_id == tx_id, Debt.origin == _OVERFLOW)
        .order_by(Debt.from_user_id)
    )
    return list(rows.scalars().all())


async def _overflow_by_debtor(session: AsyncSession, tx_id: uuid.UUID) -> dict[uuid.UUID, int]:
    return {d.from_user_id: d.amount_cents for d in await _overflow_debts(session, tx_id)}


# ── confirm via sync → overflow matérialisé (read-after-write in-transaction) ──
async def test_confirm_via_sync_materializes_overflow(household_singleton: AsyncSession) -> None:
    """`transactions/update {state:"confirmed"}` via `process_batch` → la `Debt` overflow
    est lisible dans la MÊME session. Oracle fusionné (D-S) : on prouve d'abord la
    visibilité same-session, puis `flush()`+`expire_all()`+re-`select` → l'`INSERT` SQL
    est bien ÉMIS et relisible IN-TRANSACTION (pas un objet `pending`). N.B. : ceci prouve
    le FLUSH, pas un round-trip post-commit (cf. `test_..._persists_after_commit`)."""
    seeded = await household_singleton.run_sync(
        lambda s: _seed_overflow_scenario(s, amount=10000, budget_amount=5000)
    )
    alice = await _get_user(household_singleton, seeded.alice_id)

    result = await _run(
        household_singleton,
        alice,
        _mut("transactions", "update", {"id": str(seeded.tx_id), "state": "confirmed"}),
    )

    assert result.success is True
    assert await _overflow_by_debtor(household_singleton, seeded.tx_id) == {seeded.bob_id: 2500}
    assert all(
        d.to_user_id == seeded.alice_id
        for d in await _overflow_debts(household_singleton, seeded.tx_id)
    )

    await household_singleton.flush()
    household_singleton.expire_all()
    assert await _overflow_by_debtor(household_singleton, seeded.tx_id) == {seeded.bob_id: 2500}


@pytest.mark.usefixtures("_clean_committed_db")
async def test_confirm_via_sync_persists_after_commit(committed_engine: AsyncEngine) -> None:
    """AC #1 « persiste post-commit » à la lettre : sur le moteur à commits réels, un
    `process_batch(confirm)` + `commit()` rend la `Debt` overflow visible depuis une
    transaction DISTINCTE (nouvelle session) — pas seulement un flush in-transaction.
    Le câblage du bus reste celui de la fixture autouse `_wire_sync_subscribers`."""
    sm = async_sessionmaker(committed_engine, expire_on_commit=False)

    def _seed_committed(s: Session) -> _Seeded:
        s.add(Household(name="Committed Household", base_currency="EUR"))
        s.flush()
        return _seed_overflow_scenario(s, amount=10000, budget_amount=5000)

    async with sm() as session:
        seeded = await session.run_sync(_seed_committed)
        await session.commit()

    async with sm() as session:
        alice = await _get_user(session, seeded.alice_id)
        result = await _run(
            session,
            alice,
            _mut("transactions", "update", {"id": str(seeded.tx_id), "state": "confirmed"}),
        )
        assert result.success is True
        await session.commit()

    async with sm() as session:  # fresh transaction, post-commit snapshot
        assert await _overflow_by_debtor(session, seeded.tx_id) == {seeded.bob_id: 2500}


# ── void via sync → overflow retiré (même transaction) ────────────────────────
async def test_void_via_sync_removes_overflow(household_singleton: AsyncSession) -> None:
    """`transactions/delete` (= `void`) via `process_batch` retire l'overflow dans la
    même transaction (`remove_overflow_on_void` sur `TransactionVoidedEvent`)."""
    seeded = await household_singleton.run_sync(
        lambda s: _seed_overflow_scenario(s, amount=10000, budget_amount=5000)
    )
    alice = await _get_user(household_singleton, seeded.alice_id)
    await _run(
        household_singleton,
        alice,
        _mut("transactions", "update", {"id": str(seeded.tx_id), "state": "confirmed"}),
    )
    assert await _overflow_by_debtor(household_singleton, seeded.tx_id) == {seeded.bob_id: 2500}

    result = await _run(
        household_singleton, alice, _mut("transactions", "delete", {"id": str(seeded.tx_id)})
    )

    assert result.success is True
    assert await _overflow_by_debtor(household_singleton, seeded.tx_id) == {}


async def test_void_via_state_update_removes_overflow(household_singleton: AsyncSession) -> None:
    """L'autre chemin de void du handler (`update {state:"void"}` → `_route_transition`,
    D-K) retire aussi l'overflow — les DEUX chemins déclenchent `dispatch`."""
    seeded = await household_singleton.run_sync(
        lambda s: _seed_overflow_scenario(s, amount=10000, budget_amount=5000)
    )
    alice = await _get_user(household_singleton, seeded.alice_id)
    await _run(
        household_singleton,
        alice,
        _mut("transactions", "update", {"id": str(seeded.tx_id), "state": "confirmed"}),
    )
    assert await _overflow_by_debtor(household_singleton, seeded.tx_id) == {seeded.bob_id: 2500}

    result = await _run(
        household_singleton,
        alice,
        _mut("transactions", "update", {"id": str(seeded.tx_id), "state": "void"}),
    )

    assert result.success is True
    assert await _overflow_by_debtor(household_singleton, seeded.tx_id) == {}


# ── anti-always-green : sous le budget → aucune dette ─────────────────────────
async def test_within_budget_no_overflow_via_sync(household_singleton: AsyncSession) -> None:
    """`M ≤ budget` (budget = montant) → 0 dette overflow, MÊME via le chemin sync :
    prouve que l'oracle discrimine (sinon les tests seraient toujours verts, D-U)."""
    seeded = await household_singleton.run_sync(
        lambda s: _seed_overflow_scenario(s, amount=10000, budget_amount=10000)
    )
    alice = await _get_user(household_singleton, seeded.alice_id)

    result = await _run(
        household_singleton,
        alice,
        _mut("transactions", "update", {"id": str(seeded.tx_id), "state": "confirmed"}),
    )

    assert result.success is True
    assert await _overflow_by_debtor(household_singleton, seeded.tx_id) == {}


# ── batch multi-mutations : add splits → confirm (livrable de l'issue) ─────────
async def test_add_splits_then_confirm_via_sync(household_singleton: AsyncSession) -> None:
    """SEUL cas exerçant un vrai batch multi-mutations (D-R) — colle au livrable de l'issue
    (« batch `{create_draft, add_split, transition_to_confirmed}` »). La tx draft est SEEDÉE
    (id connu, pas de threading `server_values` → S13.6) ; un seul `BatchUpload` ajoute les
    deux jambes (la classification dépasse le budget), planifie puis confirme. L'overflow
    est matérialisé in-transaction."""
    seeded = await household_singleton.run_sync(
        lambda s: _seed_overflow_scenario(
            s, amount=10000, budget_amount=5000, with_legs=False, state="draft"
        )
    )
    alice = await _get_user(household_singleton, seeded.alice_id)
    acc, cat, tx = str(seeded.account_id), str(seeded.category_id), str(seeded.tx_id)
    batch = BatchUpload(
        mutations=[
            _mut(
                "splits",
                "insert",
                {
                    "transaction_id": tx,
                    "account_id": acc,
                    "amount_cents": -10000,
                    "currency": "EUR",
                },
            ),
            _mut(
                "splits",
                "insert",
                {
                    "transaction_id": tx,
                    "account_id": acc,
                    "amount_cents": 10000,
                    "currency": "EUR",
                    "category_id": cat,
                },
            ),
            _mut("transactions", "update", {"id": tx, "state": "planned"}),
            _mut("transactions", "update", {"id": tx, "state": "confirmed"}),
        ]
    )

    results = await process_batch(household_singleton, alice, batch)

    assert all(r.success for r in results)
    assert await _overflow_by_debtor(household_singleton, seeded.tx_id) == {seeded.bob_id: 2500}
