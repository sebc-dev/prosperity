"""Helpers partagés des tests d'intégration du write upload handler (S13.x).

`mut`/`run_one` étaient copiés verbatim dans chaque suite `tests/integration/sync/`
(`test_handlers_transactions.py`, `test_handlers_debts.py`, `test_materialization_overflow.py`).
Factorisés ici (review S13.5) : un seul corps à maintenir. Module NON collecté
(pas de préfixe `test_`, précédent `_debts_helpers.py`), hors `root_package`
import-linter.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import cast
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session

from backend.modules.accounts.service.household import invalidate_household_cache
from backend.modules.auth.models import User
from backend.modules.sync.public import BatchUpload, Mutation, MutationOp, WriteResult
from backend.modules.sync.service.dispatcher import process_batch
from tests.strategies import (
    OWN_TX,
    RANDOM_ID,
    THIRD_USER,
    VICTIM_ACCOUNT,
    VICTIM_TX,
    VICTIM_USER,
    BatchSpec,
)


def mut(table: str, op: str, payload: Mapping[str, object]) -> Mutation:
    """Build a single `Mutation` (fresh `client_request_id`)."""
    return Mutation(client_request_id=uuid.uuid4(), table=table, op=op, payload=dict(payload))  # type: ignore[arg-type]


async def run_one(session: AsyncSession, user: User, mutation: Mutation) -> WriteResult:
    """Run one mutation through `process_batch` and return its single result."""
    [result] = await process_batch(session, user, BatchUpload(mutations=[mutation]))
    return result


# ── S13.9 : réalisation d'un BatchSpec abstrait + runner committant ───────────
@dataclass(frozen=True, slots=True)
class RealizeCtx:
    """Ids réels (seedés) substitués aux sentinelles d'un `BatchSpec` par `realize`."""

    victim_account_id: UUID | None = None
    victim_tx_id: UUID | None = None
    own_tx_id: UUID | None = None
    victim_user_id: UUID | None = None
    third_user_id: UUID | None = None


def _resolve(value: object, ctx: RealizeCtx) -> object:
    """Substitue récursivement les sentinelles (str / list / dict). `$random` → un
    UUID neuf (id de split inexistant : l'attaque est refusée AVANT le lookup)."""
    sentinels: dict[str, UUID | None] = {
        VICTIM_ACCOUNT: ctx.victim_account_id,
        VICTIM_TX: ctx.victim_tx_id,
        OWN_TX: ctx.own_tx_id,
        VICTIM_USER: ctx.victim_user_id,
        THIRD_USER: ctx.third_user_id,
    }
    if isinstance(value, str):
        if value == RANDOM_ID:
            return str(uuid.uuid4())
        return str(sentinels[value]) if value in sentinels else value
    if isinstance(value, list):
        return [_resolve(v, ctx) for v in value]  # type: ignore[arg-type]
    if isinstance(value, dict):
        return {k: _resolve(v, ctx) for k, v in value.items()}  # type: ignore[arg-type]
    return value


def realize(spec: BatchSpec, ctx: RealizeCtx | None = None) -> BatchUpload:
    """`BatchSpec` abstrait → `BatchUpload` concret (ids résolus, `client_request_id` neufs)."""
    rctx = ctx if ctx is not None else RealizeCtx()
    return BatchUpload(
        mutations=[
            Mutation(
                client_request_id=uuid.uuid4(),
                table=op.table,
                op=cast("MutationOp", op.op),  # OpSpec.op str ; strategies n'émettent que l'enum
                payload={k: _resolve(v, rctx) for k, v in op.fields.items()},
            )
            for op in spec.ops
        ]
    )


def run_committing_hypothesis_db_example[S, T](
    url: str,
    seed_sync: Callable[[Session], S],
    body: Callable[[AsyncSession, S], Awaitable[T]],
) -> T:
    """Variante COMMITTANTE de `run_hypothesis_db_example` (S13.9, D-ISO).

    `process_batch` committe PAR MUTATION (S13.6/ADR 0015) : un runner `begin`/
    `rollback` simple laisserait les commits FUIR entre exemples Hypothesis. Ici une
    transaction EXTERNE sur la connexion + une session `join_transaction_mode=
    "create_savepoint"` ⇒ chaque `commit()` interne devient un *release* de SAVEPOINT,
    le `rollback` externe par-exemple wipe tout (patron `db_session`).

    `invalidate_household_cache()` avant ET après (D-CACHE) : `get_household` (lu par
    `create_personal` ⇐ `accounts/insert`) mémoïse un cache PROCESS-GLOBAL que le
    rollback DB n'efface pas — sans ça l'exemple N+1 lirait le singleton fantôme de N.
    """

    async def _run() -> T:
        engine = create_async_engine(url)
        try:
            invalidate_household_cache()
            async with engine.connect() as conn:
                outer = await conn.begin()
                session_factory = async_sessionmaker(
                    bind=conn, expire_on_commit=False, join_transaction_mode="create_savepoint"
                )
                async with session_factory() as session:
                    seeded = await session.run_sync(seed_sync)
                    result = await body(session, seeded)
                await outer.rollback()
                return result
        finally:
            invalidate_household_cache()
            await engine.dispose()

    return asyncio.run(_run())
