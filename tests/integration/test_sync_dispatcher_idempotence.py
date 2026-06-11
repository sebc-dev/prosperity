"""Étape 2 du write upload handler — idempotence (S13.3 / P13.3.3).

Un `client_request_id` déjà présent dans `sync_request_log` (SCOPÉ user) → ack
`success=True` SANS ré-écrire (handler NON appelé). Exercé sur le tier
d'intégration (vrai DB hit, rollback-isolé) : on PRÉ-SÈME la ligne du journal
pour simuler l'état post-1er-write réussi (l'append réel = étape 9, S13.6). Le
sous-handler est MOCKÉ — on observe s'il est appelé (write neuf) ou court-circuité
(replay). Verrous : ordre route → auth → idempotence (D6), isolation cross-user
(Sécu F1), invariant « 0 effet DB » sur N replays.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from unittest.mock import AsyncMock

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from backend.modules.auth.models import User
from backend.modules.sync.models import SyncRequestLog
from backend.modules.sync.public import BatchUpload, Mutation, WriteResult
from backend.modules.sync.service.dispatcher import process_batch

FactoryBundle = Callable[[], Awaitable[tuple[type, type, type]]]


def _mutation(account_id: uuid.UUID, *, crid: uuid.UUID, table: str = "transactions") -> Mutation:
    return Mutation(
        client_request_id=crid,
        table=table,
        op="insert",
        payload={"account_id": str(account_id)},
    )


async def _seed_log(session: AsyncSession, *, user_id: uuid.UUID, crid: uuid.UUID) -> None:
    """Pré-sème la ligne `sync_request_log` d'un write réussi antérieur (S13.6 le
    fera réellement à l'étape 9)."""
    session.add(SyncRequestLog(user_id=user_id, client_request_id=crid, table_name="transactions"))
    await session.flush()


async def _count_log(session: AsyncSession) -> int:
    return (await session.execute(select(func.count()).select_from(SyncRequestLog))).scalar_one()


async def _run(
    session: AsyncSession, user: User, mutation: Mutation
) -> tuple[WriteResult, AsyncMock]:
    handler = AsyncMock(
        return_value=WriteResult(client_request_id=mutation.client_request_id, success=True)
    )
    [result] = await process_batch(
        session, user, BatchUpload(mutations=[mutation]), handlers={"transactions": handler}
    )
    return result, handler


async def _seed_owner(
    session: AsyncSession, factories: FactoryBundle, *, email: str
) -> tuple[User, uuid.UUID]:
    user_factory, account_factory, _ = await factories()

    def _seed(_s: Session) -> tuple[User, uuid.UUID]:
        owner = user_factory(email=email)
        acc = account_factory(owner_id=owner.id, name="Perso")
        return owner, acc.id

    return await session.run_sync(_seed)


async def test_replay_detected_acks_without_handler(
    household_singleton: AsyncSession,
    bound_account_factories: FactoryBundle,
) -> None:
    """`crid` pré-semé pour `u` (auth OK) → ack `success=True`, handler NON appelé,
    aucune nouvelle ligne dans `sync_request_log`."""
    owner, account_id = await _seed_owner(
        household_singleton, bound_account_factories, email="r1@e.com"
    )
    crid = uuid.uuid4()
    await _seed_log(household_singleton, user_id=owner.id, crid=crid)
    before = await _count_log(household_singleton)

    result, handler = await _run(household_singleton, owner, _mutation(account_id, crid=crid))

    assert result.success is True
    assert result.error is None
    handler.assert_not_awaited()
    assert await _count_log(household_singleton) == before  # 0 nouvelle ligne


async def test_fresh_crid_routes_to_handler(
    household_singleton: AsyncSession,
    bound_account_factories: FactoryBundle,
) -> None:
    """`crid` ABSENT du journal (auth OK) → handler appelé (la voie write S13.4+
    prendra le relais)."""
    owner, account_id = await _seed_owner(
        household_singleton, bound_account_factories, email="r2@e.com"
    )

    result, handler = await _run(
        household_singleton, owner, _mutation(account_id, crid=uuid.uuid4())
    )

    assert result.success is True
    handler.assert_awaited_once()


async def test_n_replays_n_acks_zero_db_effect(
    household_singleton: AsyncSession,
    bound_account_factories: FactoryBundle,
) -> None:
    """3 `process_batch` du même `crid` pré-semé → 3 acks `success=True`,
    `handler.call_count == 0` ET le compte de `sync_request_log` reste inchangé
    (invariant « 0 effet DB » — protège la régression S13.6 quand l'append sera
    câblé)."""
    owner, account_id = await _seed_owner(
        household_singleton, bound_account_factories, email="r3@e.com"
    )
    crid = uuid.uuid4()
    await _seed_log(household_singleton, user_id=owner.id, crid=crid)
    before = await _count_log(household_singleton)

    handler = AsyncMock(return_value=WriteResult(client_request_id=crid, success=True))
    for _ in range(3):
        [result] = await process_batch(
            household_singleton,
            owner,
            BatchUpload(mutations=[_mutation(account_id, crid=crid)]),
            handlers={"transactions": handler},
        )
        assert result.success is True

    assert handler.call_count == 0
    assert await _count_log(household_singleton) == before  # toujours 1 ligne


async def test_idempotence_scoped_per_user(
    household_singleton: AsyncSession,
    bound_account_factories: FactoryBundle,
) -> None:
    """Ligne `(userB, crid)` pré-semée ; le MÊME `crid` émis par `userA` (autorisé
    sur SON compte) → handler appelé (PAS d'ack idempotent) — la PK composite scope
    l'idempotence par user, fermant l'oracle cross-user (Sécu F1)."""
    user_factory, account_factory, _ = await bound_account_factories()

    def _seed(_s: Session) -> tuple[User, uuid.UUID, uuid.UUID]:
        a = user_factory(email="a@e.com")
        b = user_factory(email="b@e.com")
        acc_a = account_factory(owner_id=a.id, name="A")
        return a, acc_a.id, b.id

    user_a, account_a, user_b_id = await household_singleton.run_sync(_seed)
    crid = uuid.uuid4()
    await _seed_log(household_singleton, user_id=user_b_id, crid=crid)  # journal de B

    result, handler = await _run(household_singleton, user_a, _mutation(account_a, crid=crid))

    assert result.success is True
    handler.assert_awaited_once()  # A n'est pas idempotenté par le journal de B


async def test_auth_precedes_idempotence(
    household_singleton: AsyncSession,
    bound_account_factories: FactoryBundle,
) -> None:
    """Ligne `(u, crid)` pré-semée MAIS `u` non autorisé sur le compte → `auth_denied`
    (l'auth prime sur l'ack idempotent, ordre D6), handler non appelé."""
    user_factory, account_factory, _ = await bound_account_factories()

    def _seed(_s: Session) -> tuple[User, uuid.UUID]:
        owner = user_factory(email="o-auth@e.com")
        outsider = user_factory(email="out-auth@e.com")
        acc = account_factory(owner_id=owner.id, name="Perso")
        return outsider, acc.id

    outsider, account_id = await household_singleton.run_sync(_seed)
    crid = uuid.uuid4()
    await _seed_log(household_singleton, user_id=outsider.id, crid=crid)

    result, handler = await _run(household_singleton, outsider, _mutation(account_id, crid=crid))

    assert result.error is not None and result.error.code == "auth_denied"
    handler.assert_not_awaited()


async def test_routing_precedes_idempotence(
    household_singleton: AsyncSession,
    bound_account_factories: FactoryBundle,
) -> None:
    """Ligne `(u, crid)` pré-semée MAIS `table` non mappée → `unknown_table`
    (le court-circuit routage, étape 0, précède l'idempotence), handler non appelé."""
    owner, account_id = await _seed_owner(
        household_singleton, bound_account_factories, email="r6@e.com"
    )
    crid = uuid.uuid4()
    await _seed_log(household_singleton, user_id=owner.id, crid=crid)

    result, handler = await _run(
        household_singleton, owner, _mutation(account_id, crid=crid, table="nope")
    )

    assert result.error is not None and result.error.code == "unknown_table"
    handler.assert_not_awaited()
