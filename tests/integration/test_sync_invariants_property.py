"""Properties Hypothesis du write upload handler (S13.9 / P13.9.1) — clôt E13.

Verrouille les invariants TRANSVERSAUX de l'assemblage S13.3→S13.8 sur des batches
GÉNÉRÉS (ADR 0014, stratégie de tests §4.5/§9 — exception documentée à §4.2 :
Hypothesis sur le write upload handler est explicitement dans le scope) :

* **convergence** — pour deux ordres d'un batch de mutations INDÉPENDANTES, l'état
  final DB est identique (up-to-server-id). La convergence des dépendances ORDONNÉES
  (split AVANT confirm) est impossible en un seul batch (ids serveur, D1) et reste
  couverte example-based en S13.8 ;
* **idempotence** — rejouer le même batch (mêmes `client_request_id`) = no-op ;
* **isolation** — toute mutation cross-user (niveau dispatcher) → `auth_denied`,
  0 effet sur les entités de la victime (D-ISO-SCOPE : l'isolation service-level —
  budgets/categories/settlements/share_requests, refus 404-first en `validation_error`
  — est couverte S13.6, hors oracle `auth_denied` de cette property).

Les properties pilotent `process_batch` DIRECTEMENT (D-PATH : le chemin sync réel,
pas un mock ; pas la route HTTP — §4.2 proscrit Hypothesis sur les endpoints, et la
route est couverte example-based S13.8). Isolation per-exemple : socle `create_all`
module-scoped (gabarit `test_overflow_invariants_property.py`, vit dans
`tests/integration/` — PAS `/sync/` dont le conftest porte un autouse function-scoped)
+ `run_committing_hypothesis_db_example` (`create_savepoint` + rollback + invalidation
du cache household, D-ISO/D-CACHE). AUCUNE annotation `max_examples` : le profil défaut
est 100 (AC #194), `nightly` sweepe à 500.
"""

from __future__ import annotations

import asyncio
import datetime as dt
from collections import Counter
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import pytest
from hypothesis import HealthCheck, example, given, settings
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import Session

from backend.modules.accounts.models import Account, AccountMember, Household
from backend.modules.auth.models import User
from backend.modules.budget.models import Category
from backend.modules.sync.models import SyncRequestLog
from backend.modules.sync.public import process_batch
from backend.modules.transactions.models import Split, Transaction
from backend.shared.models import Base
from tests.integration.sync._sync_helpers import (
    RealizeCtx,
    realize,
    run_committing_hypothesis_db_example,
)
from tests.strategies import (
    BatchSpec,
    OpSpec,
    cross_user_batch_strategy,
    independent_inserts_strategy,
    op_is_attack,
    permutation_pair_strategy,
)

_PROP_SETTINGS = settings(deadline=None, suppress_health_check=[HealthCheck.too_slow])


@dataclass(frozen=True, slots=True)
class Seeded:
    caller: User
    victim_account_id: UUID | None = None
    victim_tx_id: UUID | None = None
    own_tx_id: UUID | None = None
    victim_user_id: UUID | None = None
    third_user_id: UUID | None = None


# ── socle (gabarit `overflow_prop_socle`) ──────────────────────────────────────
@pytest.fixture(scope="module")
def sync_prop_socle(postgres_container: Any) -> Iterator[str]:  # pyright: ignore[reportUnusedFunction]
    """Schéma `create_all` une fois / `drop_all` au teardown. Module-scoped ⇒ pas de
    `HealthCheck.function_scoped_fixture`. Chaque exemple seede + rollback (rien ne reste)."""
    url = str(postgres_container.get_connection_url())

    async def _ddl(create: bool) -> None:
        engine = create_async_engine(url)
        try:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all if create else Base.metadata.drop_all)
        finally:
            await engine.dispose()

    asyncio.run(_ddl(create=True))
    yield url
    asyncio.run(_ddl(create=False))


# ── seeders (run_sync) ─────────────────────────────────────────────────────────
def _seed_singleton_and_user(s: Session, email: str) -> User:
    """Seed le `Household` singleton INITIALISÉ (id par défaut = singleton, donc
    `get_household` le trouve) + un `User` ACTIF (membre du foyer)."""
    s.add(Household(name="H", base_currency="EUR", initialized_at=datetime.now(UTC)))
    s.flush()
    user = User(email=email, password_hash="x", display_name="X", role="member")
    s.add(user)
    s.flush()
    return user


def _seed_caller_sync(s: Session) -> Seeded:
    return Seeded(caller=_seed_singleton_and_user(s, "caller@ex.com"))


def _seed_isolation_sync(s: Session) -> Seeded:
    """Caller + son PROPRE compte/tx draft (vecteur D-N « jambe glissée ») + victime B
    (compte + tx draft) + tiers C (membre actif, pour le compte commun excluant le caller)."""
    caller = _seed_singleton_and_user(s, "caller@ex.com")
    own_account = Account(name="own", type="courant", currency="EUR", owner_id=caller.id)
    s.add(own_account)
    s.flush()
    own_tx = Transaction(
        account_id=own_account.id, date=dt.date(2026, 1, 1), state="draft", created_by=caller.id
    )
    s.add(own_tx)
    s.flush()

    bob = User(email="bob@ex.com", password_hash="x", display_name="B", role="member")
    s.add(bob)
    s.flush()
    bob_account = Account(name="bob", type="courant", currency="EUR", owner_id=bob.id)
    s.add(bob_account)
    s.flush()
    bob_tx = Transaction(
        account_id=bob_account.id, date=dt.date(2026, 1, 1), state="draft", created_by=bob.id
    )
    s.add(bob_tx)
    s.flush()

    carol = User(email="carol@ex.com", password_hash="x", display_name="C", role="member")
    s.add(carol)
    s.flush()
    return Seeded(
        caller=caller,
        victim_account_id=bob_account.id,
        victim_tx_id=bob_tx.id,
        own_tx_id=own_tx.id,
        victim_user_id=bob.id,
        third_user_id=carol.id,
    )


# ── oracles ────────────────────────────────────────────────────────────────────
async def _count(session: AsyncSession, model: type, *whereclause: Any) -> int:
    return int(
        (
            await session.execute(select(func.count()).select_from(model).where(*whereclause))
        ).scalar_one()
    )


async def _log_count(session: AsyncSession, *, user_id: UUID) -> int:
    return await _count(session, SyncRequestLog, SyncRequestLog.user_id == user_id)


async def _structural_snapshot(session: AsyncSession) -> Counter[tuple[str, ...]]:
    """Multiset des entités créées, UP-TO-server-id (les owner_id/ids sont exclus :
    seules forme + valeurs client comptent). Comparable entre deux runs isolés."""
    accounts = (await session.execute(select(Account.name, Account.type, Account.currency))).all()
    categories = (await session.execute(select(Category.name))).all()
    snap: Counter[tuple[str, ...]] = Counter()
    snap.update(("account", n, t, c) for n, t, c in accounts)
    snap.update(("category", n) for (n,) in categories)
    return snap


async def _victim_snapshot(session: AsyncSession, seeded: Seeded) -> tuple[object, ...]:
    """État de B + COUNTS rattachés : un insert/relation cross-user RÉUSSI changerait
    un count même sans muter la row du compte (preuve « 0 effet »)."""
    account = (
        await session.execute(
            select(Account.name, Account.type, Account.archived_at).where(
                Account.id == seeded.victim_account_id
            )
        )
    ).one()
    tx_state = (
        await session.execute(
            select(Transaction.state).where(Transaction.id == seeded.victim_tx_id)
        )
    ).scalar_one()
    n_tx = await _count(session, Transaction, Transaction.account_id == seeded.victim_account_id)
    n_splits = await _count(session, Split, Split.transaction_id == seeded.victim_tx_id)
    n_member = await _count(session, AccountMember, AccountMember.user_id == seeded.victim_user_id)
    return (tuple(account), tx_state, n_tx, n_splits, n_member)


# ── Property 1 — convergence (invariance par permutation, AC convergence) ───────
_PIN_ACC = OpSpec("accounts", "insert", {"name": "a", "type": "courant", "currency": "EUR"})
_PIN_CAT = OpSpec("categories", "insert", {"name": "c"})


@given(pair=permutation_pair_strategy())
@example(pair=(BatchSpec((_PIN_ACC, _PIN_CAT)), BatchSpec((_PIN_CAT, _PIN_ACC))))
@_PROP_SETTINGS
def test_convergence_under_permutation_property(
    sync_prop_socle: str, pair: tuple[BatchSpec, BatchSpec]
) -> None:
    spec, permuted = pair

    def _snapshot(batch_spec: BatchSpec) -> Counter[tuple[str, ...]]:
        async def _body(session: AsyncSession, seeded: Seeded) -> Counter[tuple[str, ...]]:
            results = await process_batch(session, seeded.caller, realize(batch_spec))
            assert all(r.success for r in results), results  # non-vacuité : tout commit
            return await _structural_snapshot(session)

        return run_committing_hypothesis_db_example(sync_prop_socle, _seed_caller_sync, _body)

    assert _snapshot(spec) == _snapshot(permuted)


# ── Property 2 — idempotence (replay = no-op, AC idempotence) ───────────────────
@given(spec=independent_inserts_strategy())
@_PROP_SETTINGS
def test_idempotence_replay_is_noop_property(sync_prop_socle: str, spec: BatchSpec) -> None:
    batch = realize(spec)  # crids FIXES, réutilisés au replay

    async def _body(session: AsyncSession, seeded: Seeded) -> None:
        first = await process_batch(session, seeded.caller, batch)
        assert all(r.success for r in first), first
        snap1 = await _structural_snapshot(session)
        log1 = await _log_count(session, user_id=seeded.caller.id)
        assert log1 == len(batch.mutations)  # non-vacuité : N writes journalisés
        replay = await process_batch(session, seeded.caller, batch)
        assert all(r.success for r in replay), replay  # acks success…
        assert await _structural_snapshot(session) == snap1  # …mais 0 nouvelle écriture
        assert await _log_count(session, user_id=seeded.caller.id) == log1

    run_committing_hypothesis_db_example(sync_prop_socle, _seed_caller_sync, _body)


# ── Property 3 — isolation cross-user (AC isolation, D-ISO-SCOPE) ───────────────
@given(spec=cross_user_batch_strategy())
@_PROP_SETTINGS
def test_cross_user_isolation_property(sync_prop_socle: str, spec: BatchSpec) -> None:
    async def _body(session: AsyncSession, seeded: Seeded) -> None:
        ctx = RealizeCtx(
            victim_account_id=seeded.victim_account_id,
            victim_tx_id=seeded.victim_tx_id,
            own_tx_id=seeded.own_tx_id,
            victim_user_id=seeded.victim_user_id,
            third_user_id=seeded.third_user_id,
        )
        before = await _victim_snapshot(session, seeded)
        results = await process_batch(session, seeded.caller, realize(spec, ctx))
        denied = [r for op, r in zip(spec.ops, results, strict=True) if op_is_attack(op)]
        # non-vacuité : ≥1 attaque, TOUTES refusées en `auth_denied` (fail-closed dispatcher).
        assert denied and all(
            r.error is not None and r.error.code == "auth_denied" for r in denied
        ), denied
        assert await _victim_snapshot(session, seeded) == before  # 0 effet sur les entités de B

    run_committing_hypothesis_db_example(sync_prop_socle, _seed_isolation_sync, _body)
