"""Propriété Hypothesis sur le re-balance DB de `update_share_ratio` (S05.5, P05.5.2).

⚠️ EXCEPTION ASSUMÉE au périmètre `Stratégie de tests §4.2` (« pas d'Hypothesis
sur les services ») et à l'anti-pattern §12 (« Hypothesis sur une fonction qui
écrit en DB = flaky garanti ») — mandatée par l'issue #96 : l'invariant Σ=1 du
re-balance est *quantifiable* (§4.1), donc property-testé. La flakiness est
neutralisée par un isolement strict (S05.5 D5) :

  - le **socle** (schéma + household singleton + pool de K `users`) est seedé
    **une seule fois** (committed) par une fixture **module-scoped** — donc pas
    de `HealthCheck.function_scoped_fixture` (qui sauterait sur la ré-exécution
    Hypothesis) ni de fuite d'état entre exemples ;
  - **chaque exemple** ouvre son propre engine via `asyncio.run` (asyncpg lie
    ses connexions à la boucle, donc un engine neuf par boucle), travaille dans
    une transaction et la **rollback** — aucun état de compte ne persiste hors
    de l'exemple ;
  - `postgres_container` n'expose qu'une URL (string), partageable sans conflit
    de boucle.

Budget figé localement (`max_examples=25`, `deadline=None`) : le tier DB ne suit
volontairement pas le profil `nightly` (500 × engine = trop lent).

Ne duplique pas les contrats par-endpoint de S05.4 (404 non-membre, 422 mapping,
`set(roster) != set(current)`) — couverts par `test_accounts_routes_members.py`.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.modules.accounts.domain import AccountType, AccountValidationError, MemberShare
from backend.modules.accounts.models import Account, AccountMember, Household
from backend.modules.accounts.service.members import list_members, update_share_ratio
from backend.modules.auth.models import User
from backend.shared.models import Base
from tests.strategies import share_ratios

_K = 6  # taille du pool d'users seedés (couvre n_members ∈ [2, 6])


def _user_row(uid: UUID) -> User:
    """Ligne `users` minimale et déterministe pour satisfaire la FK RESTRICT.

    `id` est FORCÉ à `uid` (le défaut `User.id = uuid4` ne suffirait pas : on
    doit ancrer les membres sur des UUID connus), l'email dérive
    DÉTERMINISTE de `uid` (pas une sequence factory → aucune collision sur
    l'index unique `lower(email)`), `password_hash` est un placeholder INERTE
    (jamais un faux hash au format réel ni un mot de passe en clair).
    """
    return User(
        id=uid,
        email=f"u-{uid}@test.local",
        password_hash="x",
        display_name="Prop User",
        role="member",
    )


def _seed_shared(session: AsyncSession, members: list[UUID], ratios: list[Decimal]) -> Account:
    """INSERT un compte commun valide + ses membres (name/currency/type NOT NULL).

    `AsyncSession.add` / `.add_all` sont synchrones (pas d'IO) ; le flush est
    awaité par l'appelant.
    """
    # `id` explicite : le défaut `Account.id = uuid4` n'est appliqué qu'au flush,
    # donc on en a besoin tout de suite pour câbler `AccountMember.account_id`.
    account = Account(
        id=uuid4(), name="Prop", type=AccountType.COURANT, currency="EUR", owner_id=None
    )
    session.add(account)
    session.add_all(
        AccountMember(account_id=account.id, user_id=uid, default_share_ratio=r)
        for uid, r in zip(members, ratios, strict=True)
    )
    return account


@pytest.fixture(scope="module")
def rebalance_socle(postgres_container) -> Iterator[tuple[str, list[UUID]]]:
    """Schéma + household singleton + K users, committed UNE fois. Renvoie (url, user_ids).

    Module-scoped (pas function-scoped) ⇒ aucun `HealthCheck.function_scoped_fixture`
    sur la ré-exécution Hypothesis. Le socle est immuable entre exemples ; seul le
    compte / les membres varient et sont rollbackés par exemple. `postgres_container`
    est session-scoped et sync : on n'en lit qu'une URL.

    Au teardown, on `drop_all` (gabarit `committed_engine`) : le socle committed
    ne doit pas fuiter sur les modules de test suivants qui partagent le même
    conteneur Postgres.
    """
    url = postgres_container.get_connection_url()
    user_ids = [uuid4() for _ in range(_K)]

    async def _setup() -> None:
        engine = create_async_engine(url)
        try:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            sm = async_sessionmaker(engine, expire_on_commit=False)
            async with sm() as s:
                s.add(Household(name="Prop", base_currency="EUR"))
                s.add_all([_user_row(uid) for uid in user_ids])
                await s.commit()
        finally:
            await engine.dispose()

    async def _teardown() -> None:
        engine = create_async_engine(url)
        try:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.drop_all)
        finally:
            await engine.dispose()

    asyncio.run(_setup())
    yield url, user_ids
    asyncio.run(_teardown())


@given(n=st.integers(min_value=2, max_value=_K), data=st.data())
@settings(max_examples=25, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_property_rebalance_keeps_sum_one(rebalance_socle, n: int, data: st.DataObject) -> None:
    # ∀ commun N∈[2,6] valide et toute édition de quote-part valide,
    # update_share_ratio MAINTIENT Σ=1 (accepté ET persisté, re-lecture confirme).
    url, pool = rebalance_socle
    members = pool[:n]
    initial = data.draw(share_ratios(n=n))  # roster de départ valide (Σ=1)
    rebalanced = data.draw(share_ratios(n=n))  # nouveau roster valide (mêmes membres)
    target = data.draw(st.sampled_from(members))

    async def _run() -> None:
        engine = create_async_engine(url)
        try:
            sm = async_sessionmaker(engine, expire_on_commit=False)
            async with sm() as s:
                await s.begin()
                acc = _seed_shared(s, members, initial)
                await s.flush()
                roster = [MemberShare(user_id=members[i], ratio=rebalanced[i]) for i in range(n)]
                result = await update_share_ratio(
                    s,
                    account_id=acc.id,
                    actor_user_id=members[0],
                    target_user_id=target,
                    roster=roster,
                )
                assert result is not None
                _, reloaded = result
                assert sum((m.default_share_ratio for m in reloaded), Decimal("0")) == Decimal(
                    "1.0000"
                )
                # Re-lecture via une requête distincte (toujours intra-transaction,
                # post-flush) : confirme Σ=1 sur l'état renvoyé par la DB, pas
                # seulement sur le tuple `result`. Pas un round-trip cross-session.
                again = await list_members(s, acc.id)
                assert sum((m.default_share_ratio for m in again), Decimal("0")) == Decimal(
                    "1.0000"
                )
                await s.rollback()  # rien ne persiste hors de l'exemple
        finally:
            await engine.dispose()

    asyncio.run(_run())


@given(
    n=st.integers(min_value=2, max_value=_K),
    bump=st.integers(min_value=1, max_value=5000),
    data=st.data(),
)
@settings(max_examples=25, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_property_inconsistent_rebalance_rejected(
    rebalance_socle, n: int, bump: int, data: st.DataObject
) -> None:
    # ∀ commun valide et tout roster Σ≠1 (on ajoute bump/10000 à un membre),
    # update_share_ratio REJETTE (AccountValidationError) et NE PERSISTE rien :
    # validate_member_set lève AVANT _apply_roster, la DB garde les ratios initiaux.
    url, pool = rebalance_socle
    members = pool[:n]
    initial = data.draw(share_ratios(n=n))
    target = data.draw(st.sampled_from(members))
    initial_by_user = dict(zip(members, initial, strict=True))

    async def _run() -> None:
        engine = create_async_engine(url)
        try:
            sm = async_sessionmaker(engine, expire_on_commit=False)
            async with sm() as s:
                await s.begin()
                acc = _seed_shared(s, members, initial)
                await s.flush()
                # Roster incohérent : même membership, mais Σ = 1 + bump/10000 != 1.
                bad = list(initial)
                bad[0] = bad[0] + Decimal(bump) / Decimal(10000)
                bad_roster = [MemberShare(user_id=members[i], ratio=bad[i]) for i in range(n)]
                with pytest.raises(AccountValidationError):
                    await update_share_ratio(
                        s,
                        account_id=acc.id,
                        actor_user_id=members[0],
                        target_user_id=target,
                        roster=bad_roster,
                    )
                # Rien persisté : les ratios en base sont toujours ceux d'origine.
                after = await list_members(s, acc.id)
                assert {m.user_id: m.default_share_ratio for m in after} == initial_by_user
                await s.rollback()
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_rebalance_50_50_to_30_70(rebalance_socle) -> None:
    """Cas concret connu, verrouillé par un test example-based dédié (S05.5 D7).

    `@example` ne peut pas fournir des valeurs tirées par `data.draw()`, donc le
    cas 0.5/0.5 → 0.3/0.7 est épinglé ici plutôt que via `@example` sur la
    propriété `st.data()`.
    """
    url, pool = rebalance_socle
    members = pool[:2]

    async def _run() -> None:
        engine = create_async_engine(url)
        try:
            sm = async_sessionmaker(engine, expire_on_commit=False)
            async with sm() as s:
                await s.begin()
                acc = _seed_shared(s, members, [Decimal("0.5000"), Decimal("0.5000")])
                await s.flush()
                roster = [
                    MemberShare(user_id=members[0], ratio=Decimal("0.3000")),
                    MemberShare(user_id=members[1], ratio=Decimal("0.7000")),
                ]
                result = await update_share_ratio(
                    s,
                    account_id=acc.id,
                    actor_user_id=members[0],
                    target_user_id=members[0],
                    roster=roster,
                )
                assert result is not None
                ratios = {m.user_id: m.default_share_ratio for m in result[1]}
                assert ratios[members[0]] == Decimal("0.3000")
                assert ratios[members[1]] == Decimal("0.7000")
                assert sum(ratios.values(), Decimal("0")) == Decimal("1.0000")
                await s.rollback()
        finally:
            await engine.dispose()

    asyncio.run(_run())
