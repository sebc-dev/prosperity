"""Routage du dispatcher PowerSync (S13.3 / P13.3.1).

`process_batch` route chaque mutation vers le sous-handler de sa `table` DANS
L'ORDRE DU TABLEAU (ADR 0014). On teste le routage en ISOLATION : les sous-
handlers sont MOCKÉS (`AsyncMock`) et injectés via le paramètre `handlers` —
aucune dépendance aux handlers réels (S13.4). La session est un SENTINEL opaque
threadé au handler : la voie routage ne touche PAS la DB (anti-pattern repo : on
ne mocke jamais une session SQLA, on la passe au handler mocké).
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator, Mapping
from unittest.mock import AsyncMock, sentinel

from hypothesis import given, settings
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.auth.domain import UserRole
from backend.modules.auth.models import User
from backend.modules.sync.schemas import BatchUpload, Mutation, WriteResult
from backend.modules.sync.service.dispatcher import Handler, process_batch
from tests.strategies import batch_upload_strategy


def _user() -> User:
    """Un `User` non persisté — opaque pour le routage (seul le handler le lit)."""
    return User(
        email="u@example.com",
        password_hash="x" * 60,
        display_name="U",
        role=UserRole.MEMBER,
    )


def _mutation(table: str = "transactions") -> Mutation:
    return Mutation(client_request_id=uuid.uuid4(), table=table, op="insert", payload={})


class _AllowAllHandlers(Mapping[str, Handler]):
    """Registre de handlers répondant à TOUTE `table` (pas un `dict` figé).

    `batch_upload_strategy` tire des `table` arbitraires (`st.text`) ; un `dict`
    figé ferait tomber le routage en `unknown_table` et TAUTOLOGISERAIT la
    property (le mapping 1:1 serait trivialement vrai sur des échecs). Chaque clé
    renvoie un handler qui ÉCHO le `client_request_id` de la mutation, pour que la
    property vérifie le routage réel, pas un ack constant.
    """

    def __getitem__(self, key: str) -> Handler:
        async def _echo(
            session: AsyncSession, user: User, mutation: Mutation
        ) -> WriteResult:
            return WriteResult(client_request_id=mutation.client_request_id, success=True)

        return _echo

    def __iter__(self) -> Iterator[str]:  # pragma: no cover - jamais énuméré
        return iter(())

    def __len__(self) -> int:  # pragma: no cover - jamais mesuré
        return 0


async def test_routes_known_table_to_handler() -> None:
    """Mutation `transactions` → handler appelé UNE fois avec `(session, user,
    mutation)` ; son `WriteResult` est dans la liste."""
    user = _user()
    m = _mutation("transactions")
    ack = WriteResult(client_request_id=m.client_request_id, success=True)
    handler = AsyncMock(return_value=ack)

    results = await process_batch(
        sentinel.session, user, BatchUpload(mutations=[m]), handlers={"transactions": handler}
    )

    handler.assert_awaited_once_with(sentinel.session, user, m)
    assert results == [ack]


async def test_unknown_table_yields_typed_error() -> None:
    """Table absente du registre → `unknown_table`, handler jamais appelé, le
    `client_request_id` de la mutation est préservé dans le `WriteResult`."""
    m = _mutation("nope")
    handler = AsyncMock()

    [result] = await process_batch(
        sentinel.session, _user(), BatchUpload(mutations=[m]), handlers={"transactions": handler}
    )

    assert result.success is False
    assert result.error is not None
    assert result.error.code == "unknown_table"
    assert result.client_request_id == m.client_request_id
    handler.assert_not_awaited()


async def test_ordering_preserved_and_continue_on_error() -> None:
    """Batch `[connue, inconnue, connue]` → 3 résultats DANS L'ORDRE ; la 2ᵉ
    (inconnue) n'interrompt pas le traitement de la 3ᵉ (continue-on-error)."""
    m1, m_bad, m3 = _mutation(), _mutation("nope"), _mutation()

    def _echo(_s: object, _u: User, mutation: Mutation) -> WriteResult:
        return WriteResult(client_request_id=mutation.client_request_id, success=True)

    handler = AsyncMock(side_effect=_echo)

    results = await process_batch(
        sentinel.session,
        _user(),
        BatchUpload(mutations=[m1, m_bad, m3]),
        handlers={"transactions": handler},
    )

    assert [r.client_request_id for r in results] == [
        m1.client_request_id,
        m_bad.client_request_id,
        m3.client_request_id,
    ]
    assert results[0].success and results[2].success
    assert results[1].error is not None and results[1].error.code == "unknown_table"
    assert handler.await_count == 2  # m1 et m3 routées, m_bad court-circuitée


async def test_empty_batch_returns_empty_list() -> None:
    """`BatchUpload(mutations=[])` → `[]` (no-op valide, D9) ; handler jamais appelé."""
    handler = AsyncMock()

    results = await process_batch(
        sentinel.session, _user(), BatchUpload(mutations=[]), handlers={"transactions": handler}
    )

    assert results == []
    handler.assert_not_awaited()


@settings(max_examples=50)
@given(batch=batch_upload_strategy())
async def test_property_one_result_per_mutation_in_order(batch: BatchUpload) -> None:
    """Verrou d'ordering : avec un registre répondant à TOUTE `table`, le résultat
    est en bijection ORDONNÉE avec `batch.mutations` (un `WriteResult` par mutation,
    même `client_request_id`, même ordre). Complète — sans dupliquer — la property
    de convergence/permutation S13.9."""
    results = await process_batch(sentinel.session, _user(), batch, handlers=_AllowAllHandlers())

    assert [r.client_request_id for r in results] == [m.client_request_id for m in batch.mutations]
