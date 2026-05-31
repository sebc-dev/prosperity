"""Integration tests for the account-creation routes (S05.3, P05.3.1).

Drives `POST /accounts/personal` and `POST /accounts/shared` over httpx
against a real Postgres (`async_client` + `auth_schema` share one
connection/transaction; the per-test rollback reverts everything). Covers:

- `owner_id` derived from the token, never the body (D3 anti-poisoning);
- the S05.2 domain rejections surfacing as a curated 422 — never a 500 —
  with the *curated* detail, not the raw domain message (C-SEC-1);
- an unknown member `user_id` → 422 via the FK 23503 path (D8), nothing
  persisted;
- the schema bounds (member cardinality, ratio bounds);
- 401 for anonymous callers (relayed by `get_current_user`).

`_reset_household_cache` (autouse) brackets every test: `get_household`'s
cache is process-local and survives the rollback, so a household primed by
one test must not leak into the next (gabarit `test_accounts_service.py`).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterator
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import get_settings
from backend.modules.accounts.models import Account, AccountMember, Household
from backend.modules.accounts.service.household import invalidate_household_cache
from backend.modules.auth.models import User
from backend.modules.auth.service.jwt import issue_access_token

_settings = get_settings()

UserMaker = Callable[..., Awaitable[User]]


@pytest.fixture(autouse=True)
def _reset_household_cache() -> Iterator[None]:  # pyright: ignore[reportUnusedFunction]
    """Cold household cache around every test (process-local, survives rollback)."""
    invalidate_household_cache()
    yield
    invalidate_household_cache()


def _bearer(user_id: UUID) -> dict[str, str]:
    return {"Authorization": f"Bearer {issue_access_token(user_id, settings=_settings)}"}


async def _seed_initialized_household(session: AsyncSession, *, base_currency: str = "EUR") -> None:
    """Seed an *initialised* singleton so `get_household` resolves (not raises)."""
    session.add(
        Household(
            name="Test Household",
            base_currency=base_currency,
            initialized_at=datetime.now(tz=UTC),
        )
    )
    await session.flush()


async def _count(session: AsyncSession, model: type[Account] | type[AccountMember]) -> int:
    return (await session.execute(select(func.count()).select_from(model))).scalar_one()


# ---------------------------------------------------------------------------
# POST /accounts/personal
# ---------------------------------------------------------------------------


async def test_post_personal_201_owner_from_token(
    async_client: AsyncClient, auth_schema: AsyncSession, bound_user_factory: UserMaker
) -> None:
    await _seed_initialized_household(auth_schema)
    owner = await bound_user_factory(email="owner@example.com")

    resp = await async_client.post(
        "/accounts/personal",
        json={"name": "Compte courant", "type": "courant", "currency": "EUR"},
        headers=_bearer(owner.id),
    )

    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["owner_id"] == str(owner.id)
    assert body["type"] == "courant"
    assert body["currency"] == "EUR"
    # 0 members for a personal account.
    assert await _count(auth_schema, AccountMember) == 0


async def test_post_personal_ignores_owner_id_in_body(
    async_client: AsyncClient, auth_schema: AsyncSession, bound_user_factory: UserMaker
) -> None:
    # An adversarial `owner_id` in the body must not change the owner: it is
    # derived server-side from the token, the body field is silently dropped.
    await _seed_initialized_household(auth_schema)
    owner = await bound_user_factory(email="real@example.com")
    other_id = uuid4()

    resp = await async_client.post(
        "/accounts/personal",
        json={
            "name": "Perso",
            "type": "courant",
            "currency": "EUR",
            "owner_id": str(other_id),
        },
        headers=_bearer(owner.id),
    )

    assert resp.status_code == 201, resp.text
    assert resp.json()["owner_id"] == str(owner.id)
    account_id = UUID(resp.json()["id"])
    persisted_owner = (
        await auth_schema.execute(select(Account.owner_id).where(Account.id == account_id))
    ).scalar_one()
    assert persisted_owner == owner.id


async def test_post_personal_401_anonymous(
    async_client: AsyncClient, auth_schema: AsyncSession
) -> None:
    await _seed_initialized_household(auth_schema)
    resp = await async_client.post(
        "/accounts/personal",
        json={"name": "Perso", "type": "courant", "currency": "EUR"},
    )
    assert resp.status_code == 401


async def test_post_personal_422_currency_mismatch(
    async_client: AsyncClient, auth_schema: AsyncSession, bound_user_factory: UserMaker
) -> None:
    await _seed_initialized_household(auth_schema)  # base EUR
    owner = await bound_user_factory(email="usd@example.com")

    resp = await async_client.post(
        "/accounts/personal",
        json={"name": "Devise", "type": "courant", "currency": "USD"},
        headers=_bearer(owner.id),
    )

    assert resp.status_code == 422, resp.text
    # Curated detail (C-SEC-1) — never the raw domain message that would echo
    # the household base currency.
    assert resp.json()["detail"] == "Account currency must match the household base currency."
    assert await _count(auth_schema, Account) == 0


async def test_post_personal_422_name_too_long(
    async_client: AsyncClient, auth_schema: AsyncSession, bound_user_factory: UserMaker
) -> None:
    await _seed_initialized_household(auth_schema)
    owner = await bound_user_factory(email="long@example.com")

    resp = await async_client.post(
        "/accounts/personal",
        json={"name": "x" * 121, "type": "courant", "currency": "EUR"},
        headers=_bearer(owner.id),
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# POST /accounts/shared
# ---------------------------------------------------------------------------


async def test_post_shared_201_creates_account_and_members(
    async_client: AsyncClient, auth_schema: AsyncSession, bound_user_factory: UserMaker
) -> None:
    await _seed_initialized_household(auth_schema)
    creator = await bound_user_factory(email="c@example.com")
    m1 = await bound_user_factory(email="m1@example.com")
    m2 = await bound_user_factory(email="m2@example.com")

    resp = await async_client.post(
        "/accounts/shared",
        json={
            "name": "Compte commun",
            "type": "courant",
            "currency": "EUR",
            "members": [
                {"user_id": str(m1.id), "default_share_ratio": "0.5"},
                {"user_id": str(m2.id), "default_share_ratio": "0.5"},
            ],
        },
        headers=_bearer(creator.id),
    )

    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["owner_id"] is None
    account_id = UUID(body["id"])
    rows = (
        (
            await auth_schema.execute(
                select(AccountMember)
                .where(AccountMember.account_id == account_id)
                .execution_options(populate_existing=True)
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == 2
    assert {r.user_id for r in rows} == {m1.id, m2.id}
    for r in rows:
        assert r.default_share_ratio == pytest.approx(0.5)


async def test_post_shared_422_one_member(
    async_client: AsyncClient, auth_schema: AsyncSession, bound_user_factory: UserMaker
) -> None:
    await _seed_initialized_household(auth_schema)
    creator = await bound_user_factory(email="solo@example.com")
    m1 = await bound_user_factory(email="only@example.com")

    resp = await async_client.post(
        "/accounts/shared",
        json={
            "name": "Solo",
            "type": "courant",
            "currency": "EUR",
            "members": [{"user_id": str(m1.id), "default_share_ratio": "1"}],
        },
        headers=_bearer(creator.id),
    )
    # `min_length=2` + `lt=1` both reject; either way it is a 422 schema error.
    assert resp.status_code == 422


async def test_post_shared_422_too_many_members(
    async_client: AsyncClient, auth_schema: AsyncSession, bound_user_factory: UserMaker
) -> None:
    await _seed_initialized_household(auth_schema)
    creator = await bound_user_factory(email="many@example.com")

    members = [{"user_id": str(uuid4()), "default_share_ratio": "0.0476"} for _ in range(21)]
    resp = await async_client.post(
        "/accounts/shared",
        json={"name": "Foule", "type": "courant", "currency": "EUR", "members": members},
        headers=_bearer(creator.id),
    )
    assert resp.status_code == 422


async def test_post_shared_422_ratio_sum_not_one(
    async_client: AsyncClient, auth_schema: AsyncSession, bound_user_factory: UserMaker
) -> None:
    await _seed_initialized_household(auth_schema)
    creator = await bound_user_factory(email="sum@example.com")
    m1 = await bound_user_factory(email="s1@example.com")
    m2 = await bound_user_factory(email="s2@example.com")

    resp = await async_client.post(
        "/accounts/shared",
        json={
            "name": "MauvaiseSomme",
            "type": "courant",
            "currency": "EUR",
            "members": [
                {"user_id": str(m1.id), "default_share_ratio": "0.5"},
                {"user_id": str(m2.id), "default_share_ratio": "0.4"},
            ],
        },
        headers=_bearer(creator.id),
    )

    assert resp.status_code == 422, resp.text
    assert resp.json()["detail"] == "Member share ratios must sum to 1."
    assert await _count(auth_schema, Account) == 0


async def test_post_shared_422_ratio_out_of_bounds(
    async_client: AsyncClient, auth_schema: AsyncSession, bound_user_factory: UserMaker
) -> None:
    await _seed_initialized_household(auth_schema)
    creator = await bound_user_factory(email="bounds@example.com")
    m1 = await bound_user_factory(email="b1@example.com")
    m2 = await bound_user_factory(email="b2@example.com")

    # A ratio of exactly 0 is rejected by the schema bound `gt=0`.
    resp = await async_client.post(
        "/accounts/shared",
        json={
            "name": "Borne",
            "type": "courant",
            "currency": "EUR",
            "members": [
                {"user_id": str(m1.id), "default_share_ratio": "0"},
                {"user_id": str(m2.id), "default_share_ratio": "1"},
            ],
        },
        headers=_bearer(creator.id),
    )
    assert resp.status_code == 422


async def test_post_shared_422_duplicate_member(
    async_client: AsyncClient, auth_schema: AsyncSession, bound_user_factory: UserMaker
) -> None:
    await _seed_initialized_household(auth_schema)
    creator = await bound_user_factory(email="dup@example.com")
    m1 = await bound_user_factory(email="d1@example.com")

    resp = await async_client.post(
        "/accounts/shared",
        json={
            "name": "Doublon",
            "type": "courant",
            "currency": "EUR",
            "members": [
                {"user_id": str(m1.id), "default_share_ratio": "0.5"},
                {"user_id": str(m1.id), "default_share_ratio": "0.5"},
            ],
        },
        headers=_bearer(creator.id),
    )

    assert resp.status_code == 422, resp.text
    assert resp.json()["detail"] == "A user cannot be listed twice in a shared account."
    assert await _count(auth_schema, Account) == 0


async def test_post_shared_422_unknown_member_user(
    async_client: AsyncClient, auth_schema: AsyncSession, bound_user_factory: UserMaker
) -> None:
    # The riskiest test of the suite (C-ARCH-2): a non-existent member
    # `user_id` survives the pure validator (Σ == 1, no duplicate) and trips
    # `fk_account_members_user_id_users` at flush — an IntegrityError(23503)
    # that crosses the (un-catching) service up to the route, mapped to 422.
    await _seed_initialized_household(auth_schema)
    creator = await bound_user_factory(email="fk@example.com")
    real = await bound_user_factory(email="exists@example.com")

    resp = await async_client.post(
        "/accounts/shared",
        json={
            "name": "FKviolation",
            "type": "courant",
            "currency": "EUR",
            "members": [
                {"user_id": str(real.id), "default_share_ratio": "0.5"},
                {"user_id": str(uuid4()), "default_share_ratio": "0.5"},  # no such user
            ],
        },
        headers=_bearer(creator.id),
    )

    assert resp.status_code == 422, resp.text
    assert resp.json()["detail"] == "A referenced member does not exist."
    # Nothing persisted: the request session rolled back its savepoint. Read
    # fresh on `auth_schema` after the response, with `populate_existing` to
    # bypass any stale identity-map copy (C-TEST-4).
    count = (
        await auth_schema.execute(
            select(func.count()).select_from(Account).execution_options(populate_existing=True)
        )
    ).scalar_one()
    assert count == 0


async def test_post_shared_422_currency_mismatch(
    async_client: AsyncClient, auth_schema: AsyncSession, bound_user_factory: UserMaker
) -> None:
    await _seed_initialized_household(auth_schema)  # base EUR
    creator = await bound_user_factory(email="cur@example.com")
    m1 = await bound_user_factory(email="cu1@example.com")
    m2 = await bound_user_factory(email="cu2@example.com")

    resp = await async_client.post(
        "/accounts/shared",
        json={
            "name": "Devise",
            "type": "courant",
            "currency": "USD",
            "members": [
                {"user_id": str(m1.id), "default_share_ratio": "0.5"},
                {"user_id": str(m2.id), "default_share_ratio": "0.5"},
            ],
        },
        headers=_bearer(creator.id),
    )
    assert resp.status_code == 422, resp.text
    assert resp.json()["detail"] == "Account currency must match the household base currency."


async def test_post_shared_401_anonymous(
    async_client: AsyncClient, auth_schema: AsyncSession
) -> None:
    await _seed_initialized_household(auth_schema)
    resp = await async_client.post(
        "/accounts/shared",
        json={
            "name": "Anon",
            "type": "courant",
            "currency": "EUR",
            "members": [
                {"user_id": str(uuid4()), "default_share_ratio": "0.5"},
                {"user_id": str(uuid4()), "default_share_ratio": "0.5"},
            ],
        },
    )
    assert resp.status_code == 401
