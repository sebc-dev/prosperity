"""Propriétés Hypothesis sur les invariants SERVICE de l'aggregate (S07.6, P07.6.2).

Verrouille trois invariants quantifiables du service lifecycle (S07.4) que les
tests example ne couvrent que ponctuellement :

  - **(1)** `update_editable_fields` sur une `confirmed` (champs *allowed*) ne
    change JAMAIS la somme des splits — les champs éditables ne touchent pas les
    montants ;
  - **(2)** `void` ne modifie AUCUN split (état terminal sans effet sur les
    montants) ;
  - **(4)** deux `confirm` consécutifs du même tx → même état final, PAS de
    second `TransactionConfirmedEvent`, pas de corruption (idempotence — 🔑
    anticipe le rejeu du write upload handler E13 / ADR 0014).

⚠️ EXCEPTION ASSUMÉE au périmètre `Stratégie de tests §4.2` (« pas d'Hypothesis
sur les services ») et à l'anti-pattern §12 (« Hypothesis sur une fonction qui
écrit en DB = flaky garanti ») — mandatée par l'issue #117 : ces invariants sont
*quantifiables*, donc property-testés. La flakiness est neutralisée par
l'isolement strict du gabarit `test_accounts_rebalance_property.py` (S05.5 D5) :

  - **socle** module-scoped (schéma + household singleton + 1 `user` + 1
    `category`) seedé UNE fois (committed) ⇒ pas de `function_scoped_fixture` sur
    la ré-exécution Hypothesis ;
  - **chaque exemple** ouvre son propre engine via `asyncio.run` (asyncpg lie ses
    connexions à la boucle), seede comptes + tx + splits, exécute le service,
    asserte, puis **rollback** — rien ne persiste hors de l'exemple ;
  - le mini-bus (S05.4) est process-global ⇒ `clear_subscribers()` encadre
    CHAQUE exemple de la propriété (4).

Budget DB figé localement (`max_examples=25`, `deadline=None`) : le tier DB ne
suit pas le profil `nightly` (200 × engine = trop lent), conformément au
précédent verrouillé `rebalance`/`archive`. Les propriétés PURES (state machine,
cohérence zero-sum à `max_examples=200`) vivent dans les tests unitaires.

Mono-devise EUR (ADR 0008) ; forme *transfert* (`distinct_accounts=True`) ⇒
`is_transfer` vrai ⇒ `assert_expenses_categorized` no-op ⇒ `confirm` sans seeder
de catégorie sur les splits (D7).
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from datetime import date
from uuid import UUID, uuid4

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.modules.accounts.domain import AccountType
from backend.modules.accounts.models import Account, Household
from backend.modules.auth.models import User
from backend.modules.budget.models import Category
from backend.modules.transactions import domain
from backend.modules.transactions.events import TransactionConfirmedEvent
from backend.modules.transactions.models import Split as SplitModel
from backend.modules.transactions.models import Transaction as TxModel
from backend.modules.transactions.service.lifecycle import (
    transition_to_confirmed,
    update_editable_fields,
    void,
)
from backend.shared.events import clear_subscribers, subscribe
from backend.shared.models import Base
from backend.shared.money import Money
from tests.strategies import balanced_splits_strategy

# A persisted leg, projection comparable: (account_id, amount_cents, currency).
Leg = tuple[UUID, int, str]

# Texte sûr pour Postgres : `codec="utf-8"` exclut les surrogates non
# encodables, `min_codepoint=1` exclut le NUL `\x00` (que les colonnes `text`/
# `varchar` PG refusent — `invalid byte sequence for encoding "UTF8": 0x00`).
# Les properties PURES (domaine, sans DB) gardent `st.text()` sans contrainte ;
# ici les valeurs sont PERSISTÉES, d'où le filtrage.
_PG_SAFE_TEXT = st.text(st.characters(codec="utf-8", min_codepoint=1), max_size=12)


def _user_row(uid: UUID) -> User:
    """Ligne `users` minimale et déterministe (FK RESTRICT `created_by`/`owner_id`).

    `id` FORCÉ à `uid` (ancrage des FK), email DÉTERMINISTE de `uid` (pas de
    collision sur l'index unique `lower(email)`), `password_hash` placeholder
    INERTE — gabarit `test_accounts_rebalance_property.py`.
    """
    return User(
        id=uid,
        email=f"u-{uid}@test.local",
        password_hash="x",
        display_name="Prop User",
        role="member",
    )


@pytest.fixture(scope="module")
def tx_invariants_socle(postgres_container) -> Iterator[tuple[str, UUID, UUID]]:
    """Schéma + household singleton + 1 user + 1 category, committed UNE fois.

    Renvoie `(url, user_id, category_id)`. Module-scoped (pas function-scoped) ⇒
    aucun `HealthCheck.function_scoped_fixture` sur la ré-exécution Hypothesis.
    Le socle est immuable entre exemples ; seuls comptes / tx / splits varient et
    sont rollbackés par exemple. `drop_all` au teardown (le socle committed ne
    doit pas fuiter sur les modules de test suivants partageant le conteneur).
    """
    url = postgres_container.get_connection_url()
    user_id = uuid4()
    category_id = uuid4()

    async def _setup() -> None:
        engine = create_async_engine(url)
        try:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            sm = async_sessionmaker(engine, expire_on_commit=False)
            async with sm() as s:
                s.add(Household(name="Prop", base_currency="EUR"))
                s.add(_user_row(user_id))
                s.add(Category(id=category_id, name="Prop Cat"))
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
    yield url, user_id, category_id
    asyncio.run(_teardown())


async def _seed_aggregate(
    session: AsyncSession,
    *,
    user_id: UUID,
    splits: tuple[domain.Split, ...],
    state: str,
) -> UUID:
    """INSERT comptes (un par account_id distinct) + tx `state` + splits ; renvoie tx.id.

    Flush PAR ÉTAGE dans l'ordre des FK (comptes → transaction → splits) : aucun
    `relationship()` n'est déclaré entre ces modèles (FK par colonne seule), donc
    l'unit-of-work n'ordonne PAS les INSERT entre mappers — un flush groupé
    insérerait les splits avant leur transaction (violation FK). Les splits sont
    seedés `category_id=None` (le `category_id: uuid4()` porté par la strategy
    viserait une catégorie inexistante → violation FK RESTRICT) : sans incidence
    ici (forme transfert ⇒ pas d'exigence de catégorisation).
    """
    account_ids = {sp.account_id for sp in splits}
    session.add_all(
        Account(id=a, name="Prop", type=AccountType.COURANT, currency="EUR", owner_id=user_id)
        for a in account_ids
    )
    await session.flush()  # comptes d'abord (tx.account_id + splits.account_id les visent)
    tx = TxModel(
        id=uuid4(),
        account_id=next(iter(account_ids)),
        created_by=user_id,
        date=date(2026, 1, 15),
        state=state,
    )
    session.add(tx)
    await session.flush()  # transaction avant les splits (splits.transaction_id la vise)
    session.add_all(
        SplitModel(
            transaction_id=tx.id,
            account_id=sp.account_id,
            category_id=None,
            amount_cents=sp.amount.amount_cents,
            currency="EUR",
        )
        for sp in splits
    )
    await session.flush()
    return tx.id


async def _reload_legs(session: AsyncSession, tx_id: UUID) -> list[Leg]:
    """Recharge les splits persistés, triés (account_id, amount_cents) — comparable.

    Re-lecture via une requête distincte (post-flush, intra-transaction) : la
    source de vérité est la DB, pas le tuple renvoyé par le service.
    """
    rows = (
        (await session.execute(select(SplitModel).where(SplitModel.transaction_id == tx_id)))
        .scalars()
        .all()
    )
    legs = [(r.account_id, r.amount_cents, r.currency) for r in rows]
    return sorted(legs, key=lambda leg: (str(leg[0]), leg[1]))


def _expected_legs(splits: tuple[domain.Split, ...]) -> list[Leg]:
    """Projection attendue des splits seedés (même tri que `_reload_legs`)."""
    legs = [(sp.account_id, sp.amount.amount_cents, "EUR") for sp in splits]
    return sorted(legs, key=lambda leg: (str(leg[0]), leg[1]))


# ---------------------------------------------------------------------------
# Propriété (1) — update_editable_fields ne touche JAMAIS les montants
# ---------------------------------------------------------------------------


@given(
    splits=balanced_splits_strategy(currency="EUR", distinct_accounts=True),
    data=st.data(),
)
@settings(max_examples=25, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_property_editable_update_preserves_sum(
    tx_invariants_socle, splits: tuple[domain.Split, ...], data: st.DataObject
) -> None:
    # ∀ confirmed zero-sum + édition de champs ALLOWED → la somme des splits
    # reste nulle ET la projection (account_id, amount_cents, currency) reste
    # IDENTIQUE au seed : les champs allowed ne touchent jamais les montants.
    url, user_id, category_id = tx_invariants_socle
    allowed: dict[str, object] = {
        "tags": tuple(data.draw(st.lists(_PG_SAFE_TEXT, max_size=3))),
        "description": data.draw(st.none() | _PG_SAFE_TEXT),
        "debt_generation_override": data.draw(
            st.sampled_from(["default", "force_full_debt", "force_no_debt"])
        ),
        "category_id": data.draw(st.sampled_from([None, category_id])),
        # `None` only: S09.1 activated the FK `share_request_id → share_requests.id`,
        # so a random UUID would now violate it. This property is about amount/
        # projection invariance under editable edits (orthogonal to the handle's
        # value); the non-null FK-valid persist path is covered by
        # `test_edit_tags_description_override_share_request_persist`.
        "share_request_id": None,
    }
    expected = _expected_legs(splits)

    async def _run() -> None:
        engine = create_async_engine(url)
        try:
            sm = async_sessionmaker(engine, expire_on_commit=False)
            async with sm() as s:
                await s.begin()
                tx_id = await _seed_aggregate(s, user_id=user_id, splits=splits, state="confirmed")
                await update_editable_fields(s, tx_id=tx_id, **allowed)
                legs = await _reload_legs(s, tx_id)
                assert legs == expected  # montants strictement inchangés
                assert sum(amount for _, amount, _ in legs) == 0  # somme toujours nulle
                await s.rollback()
        finally:
            await engine.dispose()

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# Propriété (2) — void laisse les splits IDENTIQUES
# ---------------------------------------------------------------------------


@given(
    splits=balanced_splits_strategy(currency="EUR", distinct_accounts=True),
    reason=st.text(max_size=20),
)
@settings(max_examples=25, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_property_void_preserves_splits(
    tx_invariants_socle, splits: tuple[domain.Split, ...], reason: str
) -> None:
    # ∀ confirmed + void → les splits sont INCHANGÉS et l'état devient VOID
    # (état terminal sans effet sur les montants).
    url, user_id, _category_id = tx_invariants_socle
    expected = _expected_legs(splits)

    async def _run() -> None:
        engine = create_async_engine(url)
        try:
            sm = async_sessionmaker(engine, expire_on_commit=False)
            async with sm() as s:
                await s.begin()
                tx_id = await _seed_aggregate(s, user_id=user_id, splits=splits, state="confirmed")
                result = await void(s, tx_id=tx_id, reason=reason)
                assert result.state is domain.TransactionState.VOID
                assert await _reload_legs(s, tx_id) == expected
                await s.rollback()
        finally:
            await engine.dispose()

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# Propriété (4) — double confirm = rejeu propre (idempotence, anticipe E13)
# ---------------------------------------------------------------------------


@given(splits=balanced_splits_strategy(currency="EUR", distinct_accounts=True))
@settings(max_examples=25, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_property_double_confirm_is_clean_replay(
    tx_invariants_socle, splits: tuple[domain.Split, ...]
) -> None:
    # ∀ planned zero-sum (transfert) : le 1er confirm réussit (1 event), le 2e
    # lève InvalidStateTransitionError SANS 2e event ni corruption — même état
    # final CONFIRMED, splits inchangés (D1 : rejet propre = idempotence de rejeu).
    url, user_id, _category_id = tx_invariants_socle
    expected = _expected_legs(splits)

    async def _run() -> None:
        received: list[TransactionConfirmedEvent] = []
        clear_subscribers()
        subscribe(TransactionConfirmedEvent, received.append)
        engine = create_async_engine(url)
        try:
            sm = async_sessionmaker(engine, expire_on_commit=False)
            async with sm() as s:
                await s.begin()
                tx_id = await _seed_aggregate(s, user_id=user_id, splits=splits, state="planned")

                first = await transition_to_confirmed(s, tx_id=tx_id)
                assert first.state is domain.TransactionState.CONFIRMED
                assert len(received) == 1

                with pytest.raises(domain.InvalidStateTransitionError):
                    await transition_to_confirmed(s, tx_id=tx_id)

                # Rejeu propre : aucun 2e event, état toujours CONFIRMED, splits intacts.
                assert len(received) == 1
                reloaded = await s.get(TxModel, tx_id)
                assert reloaded is not None
                assert reloaded.state == domain.TransactionState.CONFIRMED.value
                assert await _reload_legs(s, tx_id) == expected
                await s.rollback()
        finally:
            await engine.dispose()
            clear_subscribers()

    asyncio.run(_run())


def test_double_confirm_concrete(tx_invariants_socle) -> None:
    """Cas concret épinglé (gabarit `test_rebalance_50_50_to_30_70`, S05.5 D7).

    `@example` ne peut pas alimenter `data.draw()` ni les splits tirés : un
    transfert 2-jambes ±1000 EUR explicite verrouille le scénario de rejeu.
    """
    url, user_id, _category_id = tx_invariants_socle
    acc_a, acc_b = uuid4(), uuid4()
    splits = (
        domain.Split(account_id=acc_a, amount=Money(-1000, "EUR")),
        domain.Split(account_id=acc_b, amount=Money(1000, "EUR")),
    )
    expected = _expected_legs(splits)

    async def _run() -> None:
        received: list[TransactionConfirmedEvent] = []
        clear_subscribers()
        subscribe(TransactionConfirmedEvent, received.append)
        engine = create_async_engine(url)
        try:
            sm = async_sessionmaker(engine, expire_on_commit=False)
            async with sm() as s:
                await s.begin()
                tx_id = await _seed_aggregate(s, user_id=user_id, splits=splits, state="planned")

                await transition_to_confirmed(s, tx_id=tx_id)
                assert len(received) == 1
                with pytest.raises(domain.InvalidStateTransitionError):
                    await transition_to_confirmed(s, tx_id=tx_id)
                assert len(received) == 1
                assert await _reload_legs(s, tx_id) == expected
                await s.rollback()
        finally:
            await engine.dispose()
            clear_subscribers()

    asyncio.run(_run())
