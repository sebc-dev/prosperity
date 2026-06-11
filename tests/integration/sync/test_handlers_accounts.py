"""Intégration — sous-handler `accounts` (S13.4 / P13.4.2).

Route `accounts/{insert,update,delete}` vers `accounts.public`. Vérifie le forçage
des champs server-derived (`owner_id`), le gel `currency`/`type` au `rename`, et —
finding Sécu Majeur D-M — le contrôle d'appartenance de l'`insert` commun à l'étape 1
(`create_shared` n'étant PAS auth-aware). Oracle = état DB / code d'erreur.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable, Mapping
from decimal import Decimal

import pytest
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from backend.modules.accounts.models import Account, AccountMember
from backend.modules.auth.models import User
from backend.modules.sync.handlers.payloads import AccountInsertSharedPayload
from backend.modules.sync.public import BatchUpload, Mutation, WriteResult
from backend.modules.sync.service.dispatcher import process_batch

_AccountFactories = Callable[[], Awaitable[tuple[type, type, type]]]


def _mut(op: str, payload: Mapping[str, object]) -> Mutation:
    return Mutation(client_request_id=uuid.uuid4(), table="accounts", op=op, payload=dict(payload))  # type: ignore[arg-type]


async def _run(session: AsyncSession, user: User, mutation: Mutation) -> WriteResult:
    [result] = await process_batch(session, user, BatchUpload(mutations=[mutation]))
    return result


async def test_insert_personal_owned_by_user(
    initialized_household: AsyncSession, bound_account_factories: _AccountFactories
) -> None:
    user_f, _, _ = await bound_account_factories()
    owner = await initialized_household.run_sync(lambda _s: user_f(email="p@ex.com"))

    payload = {"name": "Courant", "type": "courant", "currency": "EUR"}
    result = await _run(initialized_household, owner, _mut("insert", payload))

    assert result.success is True
    acc = (
        await initialized_household.execute(select(Account).where(Account.name == "Courant"))
    ).scalar_one()
    assert acc.owner_id == owner.id


async def test_insert_rejects_owner_id_in_payload(
    household_singleton: AsyncSession, bound_account_factories: _AccountFactories
) -> None:
    user_f, _, _ = await bound_account_factories()
    owner = await household_singleton.run_sync(lambda _s: user_f(email="p2@ex.com"))
    payload = {"name": "X", "type": "courant", "currency": "EUR", "owner_id": str(uuid.uuid4())}
    with pytest.raises(ValidationError):
        await _run(household_singleton, owner, _mut("insert", payload))


async def test_insert_shared_creates_members(
    initialized_household: AsyncSession, bound_account_factories: _AccountFactories
) -> None:
    user_f, _, _ = await bound_account_factories()

    def _seed(_s: Session) -> tuple[User, uuid.UUID]:
        a = user_f(email="a@ex.com")
        b = user_f(email="b@ex.com")
        return a, b.id

    caller, other_id = await initialized_household.run_sync(_seed)
    payload = {
        "name": "Commun",
        "type": "courant",
        "currency": "EUR",
        "members": [
            {"user_id": str(caller.id), "ratio": "0.5"},
            {"user_id": str(other_id), "ratio": "0.5"},
        ],
    }
    result = await _run(initialized_household, caller, _mut("insert", payload))

    assert result.success is True
    acc = (
        await initialized_household.execute(select(Account).where(Account.name == "Commun"))
    ).scalar_one()
    assert acc.owner_id is None
    members = (
        await initialized_household.execute(
            select(func.count())
            .select_from(AccountMember)
            .where(AccountMember.account_id == acc.id)
        )
    ).scalar_one()
    assert members == 2


async def test_shared_insert_denied_when_caller_absent(
    household_singleton: AsyncSession, bound_account_factories: _AccountFactories
) -> None:
    """D-M : le caller DOIT figurer parmi les membres, sinon `auth_denied`."""
    user_f, _, _ = await bound_account_factories()

    def _seed(_s: Session) -> tuple[User, uuid.UUID, uuid.UUID]:
        caller = user_f(email="c@ex.com")
        m1 = user_f(email="m1@ex.com")
        m2 = user_f(email="m2@ex.com")
        return caller, m1.id, m2.id

    caller, m1, m2 = await household_singleton.run_sync(_seed)
    payload = {
        "name": "Tiers",
        "type": "courant",
        "currency": "EUR",
        "members": [{"user_id": str(m1), "ratio": "0.5"}, {"user_id": str(m2), "ratio": "0.5"}],
    }
    result = await _run(household_singleton, caller, _mut("insert", payload))

    assert result.success is False
    assert result.error is not None
    assert result.error.code == "auth_denied"


async def test_shared_insert_denied_when_member_not_active(
    household_singleton: AsyncSession, bound_account_factories: _AccountFactories
) -> None:
    """D-M : un `user_id` qui n'est pas un membre actif du foyer → `auth_denied`."""
    user_f, _, _ = await bound_account_factories()
    caller = await household_singleton.run_sync(lambda _s: user_f(email="c2@ex.com"))
    payload = {
        "name": "Fantome",
        "type": "courant",
        "currency": "EUR",
        "members": [
            {"user_id": str(caller.id), "ratio": "0.5"},
            {"user_id": str(uuid.uuid4()), "ratio": "0.5"},  # inexistant → non actif
        ],
    }
    result = await _run(household_singleton, caller, _mut("insert", payload))

    assert result.success is False
    assert result.error is not None
    assert result.error.code == "auth_denied"


@pytest.mark.parametrize(
    "members",
    [
        "not-a-list",  # `members` n'est pas une liste
        [],  # liste vide
        ["not-a-dict"],  # un membre n'est pas un objet
        [{"ratio": "1.0"}],  # `user_id` absent → non coercible
    ],
)
async def test_shared_insert_malformed_members_denied(
    household_singleton: AsyncSession, bound_account_factories: _AccountFactories, members: object
) -> None:
    """Étape 1 D-M : un bloc `members` malformé → `_member_user_ids` fail-closed →
    `auth_denied`, SANS exception (le handler / Pydantic n'est jamais atteint)."""
    user_f, _, _ = await bound_account_factories()
    caller = await household_singleton.run_sync(lambda _s: user_f(email="mal@ex.com"))
    payload = {"name": "X", "type": "courant", "currency": "EUR", "members": members}
    result = await _run(household_singleton, caller, _mut("insert", payload))

    assert result.success is False
    assert result.error is not None
    assert result.error.code == "auth_denied"


async def test_update_renames_only(
    household_singleton: AsyncSession, bound_account_factories: _AccountFactories
) -> None:
    user_f, account_f, _ = await bound_account_factories()

    def _seed(_s: Session) -> tuple[User, uuid.UUID]:
        owner = user_f(email="r@ex.com")
        return owner, account_f(owner_id=owner.id, name="Avant").id

    owner, account_id = await household_singleton.run_sync(_seed)
    await _run(household_singleton, owner, _mut("update", {"id": str(account_id), "name": "Après"}))
    acc = await household_singleton.get(Account, account_id)
    assert acc is not None
    assert acc.name == "Après"


async def test_rename_rejects_frozen_currency(
    household_singleton: AsyncSession, bound_account_factories: _AccountFactories
) -> None:
    user_f, account_f, _ = await bound_account_factories()

    def _seed(_s: Session) -> tuple[User, uuid.UUID]:
        owner = user_f(email="r2@ex.com")
        return owner, account_f(owner_id=owner.id).id

    owner, account_id = await household_singleton.run_sync(_seed)
    payload = {"id": str(account_id), "name": "Y", "currency": "USD"}  # currency gelée → absente
    with pytest.raises(ValidationError):
        await _run(household_singleton, owner, _mut("update", payload))


async def test_delete_archives(
    household_singleton: AsyncSession, bound_account_factories: _AccountFactories
) -> None:
    user_f, account_f, _ = await bound_account_factories()

    def _seed(_s: Session) -> tuple[User, uuid.UUID]:
        owner = user_f(email="d@ex.com")
        return owner, account_f(owner_id=owner.id).id

    owner, account_id = await household_singleton.run_sync(_seed)
    result = await _run(household_singleton, owner, _mut("delete", {"id": str(account_id)}))

    assert result.success is True
    acc = await household_singleton.get(Account, account_id)
    assert acc is not None
    assert acc.archived_at is not None


async def test_update_inaccessible_account_denied(
    household_singleton: AsyncSession, bound_account_factories: _AccountFactories
) -> None:
    user_f, account_f, _ = await bound_account_factories()

    def _seed(_s: Session) -> tuple[User, uuid.UUID]:
        intruder = user_f(email="i@ex.com")
        other = user_f(email="ot@ex.com")
        return intruder, account_f(owner_id=other.id).id

    intruder, foreign_id = await household_singleton.run_sync(_seed)
    result = await _run(
        household_singleton, intruder, _mut("update", {"id": str(foreign_id), "name": "Z"})
    )

    assert result.success is False
    assert result.error is not None
    assert result.error.code == "auth_denied"


def test_member_share_ratio_is_decimal() -> None:
    """Garde unitaire : la quote-part wire est bien convertie en `Decimal` pour
    `MemberShare` (pas de float)."""
    payload = AccountInsertSharedPayload.model_validate(
        {
            "name": "C",
            "type": "courant",
            "currency": "EUR",
            "members": [
                {"user_id": str(uuid.uuid4()), "ratio": "0.25"},
                {"user_id": str(uuid.uuid4()), "ratio": "0.75"},
            ],
        }
    )
    shares = payload.to_member_shares()
    assert {s.ratio for s in shares} == {Decimal("0.25"), Decimal("0.75")}
