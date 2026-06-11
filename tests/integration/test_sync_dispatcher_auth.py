"""Étape 1 du write upload handler — auth / RBAC (S13.3 / P13.3.2).

`process_batch` refuse (`auth_denied`) une mutation que `user` n'a pas le droit
de faire, via le registre central `PERMISSION_CHECKS` → `account_is_accessible`
(`accounts.public`). Exercé sur le tier d'INTÉGRATION (vrai DB hit, rollback-isolé
via `household_singleton`) : on n'a JAMAIS le droit de mocker `account_is_accessible`
(frontière interne au module accounts) — on mocke le SOUS-HANDLER (frontière
cross-module légitime) et on observe s'il est appelé (auth passée) ou non (refusée).
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from unittest.mock import AsyncMock

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from backend.modules.auth.domain import UserRole
from backend.modules.auth.models import User
from backend.modules.sync.public import BatchUpload, Mutation, WriteResult
from backend.modules.sync.service.dispatcher import process_batch

FactoryBundle = Callable[[], Awaitable[tuple[type, type, type]]]


def _mutation(payload: dict[str, object], *, op: str = "insert") -> Mutation:
    return Mutation(
        client_request_id=uuid.uuid4(),
        table="transactions",
        op=op,  # type: ignore[arg-type]
        payload=payload,
    )


async def _run(
    session: AsyncSession, user: User, mutation: Mutation
) -> tuple[WriteResult, AsyncMock]:
    """Route `mutation` par `user` avec un sous-handler `transactions` MOCKÉ (ack
    `success=True`). Renvoie `(result, handler_mock)` — l'appelant assert si le
    handler a été appelé (auth OK) ou non (refusée)."""
    handler = AsyncMock(
        return_value=WriteResult(client_request_id=mutation.client_request_id, success=True)
    )
    [result] = await process_batch(
        session, user, BatchUpload(mutations=[mutation]), handlers={"transactions": handler}
    )
    return result, handler


# ── Cas autorisés ────────────────────────────────────────────────────────────


async def test_member_of_shared_account_authorized(
    household_singleton: AsyncSession,
    bound_account_factories: FactoryBundle,
) -> None:
    """Un membre d'un compte commun peut y créer une transaction → handler appelé."""
    user_factory, account_factory, member_factory = await bound_account_factories()

    def _seed(_s: Session) -> tuple[User, uuid.UUID]:
        m1 = user_factory(email="m1@example.com")
        m2 = user_factory(email="m2@example.com")
        shared = account_factory(owner_id=None, name="Commun")
        member_factory(account_id=shared.id, user_id=m1.id)
        member_factory(account_id=shared.id, user_id=m2.id)
        return m1, shared.id

    member, account_id = await household_singleton.run_sync(_seed)
    result, handler = await _run(
        household_singleton, member, _mutation({"account_id": str(account_id)})
    )

    assert result.success is True
    handler.assert_awaited_once()


async def test_owner_of_personal_account_authorized(
    household_singleton: AsyncSession,
    bound_account_factories: FactoryBundle,
) -> None:
    """L'owner d'un compte perso peut y créer une transaction → handler appelé."""
    user_factory, account_factory, _ = await bound_account_factories()

    def _seed(_s: Session) -> tuple[User, uuid.UUID]:
        owner = user_factory(email="owner@example.com")
        acc = account_factory(owner_id=owner.id, name="Perso")
        return owner, acc.id

    owner, account_id = await household_singleton.run_sync(_seed)
    result, handler = await _run(
        household_singleton, owner, _mutation({"account_id": str(account_id)})
    )

    assert result.success is True
    handler.assert_awaited_once()


async def test_transfer_all_accounts_accessible_authorized(
    household_singleton: AsyncSession,
    bound_account_factories: FactoryBundle,
) -> None:
    """Transfert touchant ≥ 2 comptes TOUS accessibles → autorisé (verrou Sécu
    Majeur, sens positif). Racine A + splits sur A et B, l'user accède à A et B."""
    user_factory, account_factory, _ = await bound_account_factories()

    def _seed(_s: Session) -> tuple[User, uuid.UUID, uuid.UUID]:
        owner = user_factory(email="owner2@example.com")
        a = account_factory(owner_id=owner.id, name="A")
        b = account_factory(owner_id=owner.id, name="B")
        return owner, a.id, b.id

    owner, a_id, b_id = await household_singleton.run_sync(_seed)
    payload: dict[str, object] = {
        "account_id": str(a_id),
        "splits": [{"account_id": str(a_id)}, {"account_id": str(b_id)}],
    }
    result, handler = await _run(household_singleton, owner, _mutation(payload))

    assert result.success is True
    handler.assert_awaited_once()


# ── Cas refusés ──────────────────────────────────────────────────────────────


async def test_non_member_other_account_denied(
    household_singleton: AsyncSession,
    bound_account_factories: FactoryBundle,
) -> None:
    """Un tiers (ni owner ni membre) → `auth_denied`, handler non appelé."""
    user_factory, account_factory, _ = await bound_account_factories()

    def _seed(_s: Session) -> tuple[User, uuid.UUID]:
        owner = user_factory(email="o3@example.com")
        outsider = user_factory(email="out3@example.com")
        acc = account_factory(owner_id=owner.id, name="Perso")
        return outsider, acc.id

    outsider, account_id = await household_singleton.run_sync(_seed)
    result, handler = await _run(
        household_singleton, outsider, _mutation({"account_id": str(account_id)})
    )

    assert result.error is not None and result.error.code == "auth_denied"
    handler.assert_not_awaited()


async def test_transfer_one_leg_inaccessible_denied(
    household_singleton: AsyncSession,
    bound_account_factories: FactoryBundle,
) -> None:
    """Transfert : une jambe sur un compte accessible + une jambe sur un compte
    d'AUTRUI → `auth_denied`, handler non appelé (CŒUR du finding Sécu Majeur : un
    compte racine accessible ne « blanchit » pas un split inaccessible — on vérifie
    TOUS les comptes touchés, pas seulement le racine)."""
    user_factory, account_factory, _ = await bound_account_factories()

    def _seed(_s: Session) -> tuple[User, uuid.UUID, uuid.UUID]:
        owner = user_factory(email="o4@example.com")
        stranger = user_factory(email="s4@example.com")
        mine = account_factory(owner_id=owner.id, name="Mine")
        theirs = account_factory(owner_id=stranger.id, name="Theirs")
        return owner, mine.id, theirs.id

    owner, mine_id, theirs_id = await household_singleton.run_sync(_seed)
    payload: dict[str, object] = {
        "account_id": str(mine_id),  # racine accessible
        "splits": [{"account_id": str(mine_id)}, {"account_id": str(theirs_id)}],
    }
    result, handler = await _run(household_singleton, owner, _mutation(payload))

    assert result.error is not None and result.error.code == "auth_denied"
    handler.assert_not_awaited()


async def test_admin_not_exempt(
    household_singleton: AsyncSession,
    bound_account_factories: FactoryBundle,
) -> None:
    """`account_is_accessible` est role-blind : un admin non-membre du compte est
    refusé comme n'importe qui (AC F03) → `auth_denied`."""
    user_factory, account_factory, _ = await bound_account_factories()

    def _seed(_s: Session) -> tuple[User, uuid.UUID]:
        owner = user_factory(email="o5@example.com")
        admin = user_factory(email="admin5@example.com", role=UserRole.ADMIN)
        acc = account_factory(owner_id=owner.id, name="Perso")
        return admin, acc.id

    admin, account_id = await household_singleton.run_sync(_seed)
    result, handler = await _run(
        household_singleton, admin, _mutation({"account_id": str(account_id)})
    )

    assert result.error is not None and result.error.code == "auth_denied"
    handler.assert_not_awaited()


async def test_unmapped_table_op_denied(
    household_singleton: AsyncSession,
    bound_account_factories: FactoryBundle,
) -> None:
    """`(table, op)` sans check enregistré (`transactions`/`update` n'est PAS dans
    `PERMISSION_CHECKS` en S13.3) → fail-closed `auth_denied` (D4), même si le
    handler est routable."""
    user_factory, account_factory, _ = await bound_account_factories()

    def _seed(_s: Session) -> tuple[User, uuid.UUID]:
        owner = user_factory(email="o6@example.com")
        acc = account_factory(owner_id=owner.id, name="Perso")
        return owner, acc.id

    owner, account_id = await household_singleton.run_sync(_seed)
    result, handler = await _run(
        household_singleton, owner, _mutation({"account_id": str(account_id)}, op="update")
    )

    assert result.error is not None and result.error.code == "auth_denied"
    handler.assert_not_awaited()


# ── Fail-closed sur payload douteux (best-effort AVANT validation Pydantic) ────


async def test_fail_closed_payloads_deny_without_exception(
    household_singleton: AsyncSession,
    bound_account_factories: FactoryBundle,
) -> None:
    """Aucun compte exploitable / référence malformée / structure non-scalaire →
    `auth_denied` SANS exception qui remonte (`_referenced_account_ids` fail-closed).
    Couvre toutes les branches douteuses en un test paramétrique."""
    user_factory, _account_factory, _ = await bound_account_factories()

    def _seed(_s: Session) -> User:
        return user_factory(email="o7@example.com")

    user = await household_singleton.run_sync(_seed)

    doubtful_payloads: list[dict[str, object]] = [
        {},  # aucun compte
        {"splits": []},  # liste vide → aucun compte
        {"account_id": "not-a-uuid"},  # racine malformée
        {"account_id": ["x"]},  # non-scalaire (list)
        {"account_id": {"a": 1}},  # non-scalaire (dict)
        {"account_id": True},  # non-scalaire (bool)
        {"splits": "oops"},  # splits pas une liste
        {"splits": [{}]},  # split sans account_id
        {"splits": [{"account_id": [42]}]},  # split.account_id non-scalaire
    ]

    for payload in doubtful_payloads:
        result, handler = await _run(household_singleton, user, _mutation(payload))
        assert result.error is not None and result.error.code == "auth_denied", payload
        handler.assert_not_awaited()
