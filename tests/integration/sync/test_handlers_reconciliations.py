"""Intégration — sous-handler `reconciliations` placeholder V1 (S13.4 / P13.4.5).

Le check « membre actif » (D-H) PASSE puis le handler renvoie un échec EXPLICITE
`not_implemented_yet` — distinct d'un `auth_denied` (étape 1) ou d'un `unknown_table`
(routage), pour toute op. Aucune logique métier, 0 arc import-linter.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.auth.models import User
from backend.modules.sync.public import BatchUpload, Mutation, WriteResult
from backend.modules.sync.service.dispatcher import process_batch

_UserFactory = Callable[..., Awaitable[User]]


def _mut(op: str) -> Mutation:
    return Mutation(client_request_id=uuid.uuid4(), table="reconciliations", op=op, payload={})  # type: ignore[arg-type]


async def _run(session: AsyncSession, user: User, mutation: Mutation) -> WriteResult:
    [result] = await process_batch(session, user, BatchUpload(mutations=[mutation]))
    return result


@pytest.mark.parametrize("op", ["insert", "update", "delete"])
async def test_any_op_returns_not_implemented_yet(
    household_singleton: AsyncSession, bound_user_factory: _UserFactory, op: str
) -> None:
    user = await bound_user_factory(email=f"rec-{op}@ex.com")
    result = await _run(household_singleton, user, _mut(op))

    assert result.success is False
    assert result.error is not None
    assert result.error.code == "not_implemented_yet"


async def test_passes_step1_then_handler_runs(
    household_singleton: AsyncSession, bound_user_factory: _UserFactory
) -> None:
    """Distinct d'`auth_denied` : l'étape 1 (membre actif) PASSE, puis le handler
    s'exécute et renvoie son échec dédié — preuve que le placeholder est ATTEINT."""
    user = await bound_user_factory(email="rec-step1@ex.com")
    result = await _run(household_singleton, user, _mut("insert"))

    assert result.error is not None
    assert result.error.code != "auth_denied"
    assert result.error.code != "unknown_table"
