"""Properties Hypothesis PERSISTÉES des invariants overflow F10 (S11.5 / P11.5.1.b).

Au-delà des properties du domaine pur (S11.2) et de celles anticipées en S11.3
(D15 : conservation `default`, idempotence mono-ratio, fidélité multi-membre),
cette suite éprouve les invariants sur l'état **réellement persisté** via le
materializer S11.3, sur l'espace de scénarios complet généré par
`overflow_scenario_strategy` (roster `Σ=1` 2..5 membres, override aléatoire,
budget ∅/présent). Quatre invariants :

* **idempotence par ré-émission d'event** — `dispatch(TransactionConfirmedEvent)`
  deux fois ⇒ set de `Debt` overflow byte-identique (`ON CONFLICT` + prune, ADR
  0002). Snapshot 6-uple `(tx, from, to, amount_cents, share_ratio, currency)`
  (toutes les colonnes mutables de l'upsert) ;
* **`force_no_debt` inerte** — aucune `Debt` overflow, quel que soit le dépassement ;
* **`force_full_debt` : budget court-circuité + orientation + arrondi-0** — base = M
  (budget ignoré bien que présent), unique dette O→P `round(M × (1 − s_payer))`,
  omise à l'arrondi-0. ⚠️ l'oracle réutilise `apply_ratio` (restitution
  définitionnelle de la forme close de l'AC #168 (3)) : la *conservation* réelle
  `Σ E = max(0, ΣM − budget)` est couverte par S11.3 `test_conservation_property` ;
* **exclusivité d'origine** — une `Debt` `personal_share_request` co-présente sur
  la MÊME paire `(tx, from, to)` qu'une dette overflow n'est jamais altérée (AC
  opposable). `assume(expected > 0)` garantit qu'un overflow EST écrit sur la paire
  (test non vacant).

Isolation (gabarit `overflow_socle` S11.3) : schéma `create_all` une fois
(`overflow_prop_socle`, scope module ⇒ pas de `HealthCheck.function_scoped_fixture`),
chaque exemple seede dans un `run_sync` puis `rollback` ⇒ aucun état inter-exemples.
Câblage `materialize_overflow` sur le bus au scope module (`dispatch` ré-émet l'event).
Seeds en forme canonique B (ADR 0017) : funding leg (`category_id=NULL`) +
classification leg (catégorisée), même compte commun, zero-sum.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Iterator
from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

import pytest
from hypothesis import HealthCheck, assume, given, settings
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session

from backend.modules.accounts.models import Account, AccountMember, Household
from backend.modules.auth.models import User
from backend.modules.budget.models import Budget, BudgetContributor, Category
from backend.modules.debts.models import Debt
from backend.modules.debts.service.overflow_materializer import materialize_overflow
from backend.modules.transactions.events import TransactionConfirmedEvent
from backend.modules.transactions.models import Split, Transaction
from backend.shared.events import clear_subscribers, dispatch, subscribe_async
from backend.shared.models import Base
from backend.shared.money import Money
from tests.strategies import OverflowScenario, overflow_scenario_strategy

_OVERFLOW = "shared_account_overflow"


@dataclass(frozen=True, slots=True)
class _Seeded:
    account_id: UUID
    tx_ids: list[UUID]
    payer: UUID  # = members[0].user_id (créancier)
    member_ids: list[UUID]


# ---------------------------------------------------------------------------
# Socle & câblage (gabarit `overflow_socle` / `_wire_overflow` S11.3)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def overflow_prop_socle(postgres_container) -> Iterator[str]:  # pyright: ignore[reportUnusedFunction]
    """Schéma `create_all` une fois / `drop_all` au teardown (gabarit `overflow_socle`).

    Module-scoped ⇒ pas de `HealthCheck.function_scoped_fixture` au re-run Hypothesis.
    Chaque exemple seede dans une transaction et `rollback` ⇒ rien ne persiste.
    """
    url = postgres_container.get_connection_url()

    async def _setup() -> None:
        engine = create_async_engine(url)
        try:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
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
    yield url
    asyncio.run(_teardown())


@pytest.fixture(scope="module", autouse=True)
def _wire() -> Iterator[None]:  # pyright: ignore[reportUnusedFunction]
    """Souscrit UNIQUEMENT `materialize_overflow` (la suite éprouve le seul chemin
    `confirmed`). Scope module ⇒ pas de fixture function-scoped sous `@given`.
    `clear_subscribers()` en setup ET teardown (bus process-global, pas de fuite)."""
    clear_subscribers()
    subscribe_async(TransactionConfirmedEvent, materialize_overflow)
    yield
    clear_subscribers()


# ---------------------------------------------------------------------------
# Seeder (run_sync) + helpers d'assertion overflow
# ---------------------------------------------------------------------------


def _seed_scenario_sync(s: Session, sc: OverflowScenario) -> _Seeded:
    """Matérialise un `OverflowScenario` : Household + Users + compte commun +
    membres (quote-parts) + catégorie + budget optionnel + 1 dépense forme-B par tx
    (`created_by` = payeur = members[0]). Calque `_seed_period_sync` (S11.3)."""
    s.add(Household(name="H", base_currency="EUR"))
    s.flush()
    member_ids = [m.user_id for m in sc.account.members]
    s.add_all(
        [
            User(
                id=m.user_id,
                email=f"{m.user_id.hex[:8]}@e.com",
                password_hash="x",
                display_name="X",
                role="member",
            )
            for m in sc.account.members
        ]
    )
    s.flush()
    account = Account(name="Commun", type="courant", currency="EUR", owner_id=None)
    s.add(account)
    s.flush()
    s.add_all(
        [
            AccountMember(account_id=account.id, user_id=m.user_id, default_share_ratio=m.ratio)
            for m in sc.account.members
        ]
    )
    cat = Category(name="Courses")
    s.add(cat)
    s.flush()
    payer = member_ids[0]

    if sc.budget is not None:
        budget = Budget(
            category_id=cat.id,
            period_kind=sc.budget.period_kind,
            period_start=sc.budget.period_start,
            amount_cents=sc.budget.amount_cents,
            currency="EUR",
            scope=sc.budget.scope,
            created_by=payer,
        )
        s.add(budget)
        s.flush()
        s.add_all([BudgetContributor(budget_id=budget.id, user_id=uid) for uid in member_ids])
        s.flush()

    tx_ids: list[UUID] = []
    for tx in sc.txs:
        t = Transaction(
            account_id=account.id,
            date=tx.on,
            state="confirmed",
            created_by=payer,
            debt_generation_override=tx.override,
        )
        s.add(t)
        s.flush()
        s.add_all(
            [
                Split(
                    transaction_id=t.id,
                    account_id=account.id,
                    category_id=None,
                    amount_cents=-tx.amount_cents,
                    currency="EUR",
                ),
                Split(
                    transaction_id=t.id,
                    account_id=account.id,
                    category_id=cat.id,
                    amount_cents=tx.amount_cents,
                    currency="EUR",
                ),
            ]
        )
        s.flush()
        tx_ids.append(t.id)

    return _Seeded(account_id=account.id, tx_ids=tx_ids, payer=payer, member_ids=member_ids)


async def _overflow_set(s: AsyncSession) -> set[tuple[UUID, UUID, UUID, int, Decimal, str]]:
    """Snapshot 6-uple `(tx, from, to, amount_cents, share_ratio, currency)` des dettes
    overflow — TOUTES les colonnes mutables de l'upsert (M2) ⇒ un upsert oubliant
    `share_ratio`/`currency` à la ré-émission serait détecté."""
    rows = await s.execute(
        select(
            Debt.source_transaction_id,
            Debt.from_user_id,
            Debt.to_user_id,
            Debt.amount_cents,
            Debt.share_ratio,
            Debt.currency,
        ).where(Debt.origin == _OVERFLOW)
    )
    return {(r[0], r[1], r[2], r[3], r[4], r[5]) for r in rows.all()}


async def _overflow_by_debtor(s: AsyncSession, tx_id: UUID) -> dict[UUID, int]:
    rows = await s.execute(
        select(Debt.from_user_id, Debt.amount_cents).where(
            Debt.origin == _OVERFLOW, Debt.source_transaction_id == tx_id
        )
    )
    return {uid: cents for uid, cents in rows.all()}


def _run_scenario(
    url: str,
    sc: OverflowScenario,
    body: Callable[[AsyncSession, _Seeded], Awaitable[None]],
) -> None:
    """Engine + session par exemple (gabarit D15) : `begin` → seed → `body` → `rollback`.

    Un nouvel `engine` par exemple (proven S11.3) évite les soucis d'event-loop avec
    Hypothesis ; le `rollback` + `dispose` garantissent l'isolation inter-exemples."""

    async def _run() -> None:
        engine = create_async_engine(url)
        try:
            sm = async_sessionmaker(engine, expire_on_commit=False)
            async with sm() as s:
                await s.begin()
                seeded = await s.run_sync(lambda sync: _seed_scenario_sync(sync, sc))
                await body(s, seeded)
                await s.rollback()
        finally:
            await engine.dispose()

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# Property 1 — idempotence par ré-émission d'event (AC #168 (1), ADR 0002)
# ---------------------------------------------------------------------------


@given(sc=overflow_scenario_strategy())
@settings(max_examples=20, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_idempotence_reemit_property(overflow_prop_socle: str, sc: OverflowScenario) -> None:
    async def _body(s: AsyncSession, seeded: _Seeded) -> None:
        events = [
            TransactionConfirmedEvent(transaction_id=t, account_id=seeded.account_id)
            for t in seeded.tx_ids
        ]
        for ev in events:
            await dispatch(s, ev)
        first = await _overflow_set(s)
        # S2 — verrou d'orientation sur le plus grand espace : toute dette va vers le payeur.
        assert all(to == seeded.payer for (_tx, _frm, to, _amt, _ratio, _cur) in first)
        # RÉ-ÉMISSION de l'event via le bus (pas re-appel pur) ⇒ ON CONFLICT + prune.
        for ev in events:
            await dispatch(s, ev)
        assert await _overflow_set(s) == first

    _run_scenario(overflow_prop_socle, sc, _body)


# ---------------------------------------------------------------------------
# Property 2 — `force_no_debt` inerte (AC #168 (2))
# ---------------------------------------------------------------------------


@given(sc=overflow_scenario_strategy(override="force_no_debt"))
@settings(max_examples=20, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_force_no_debt_inert_property(overflow_prop_socle: str, sc: OverflowScenario) -> None:
    async def _body(s: AsyncSession, seeded: _Seeded) -> None:
        for t in seeded.tx_ids:
            await dispatch(
                s, TransactionConfirmedEvent(transaction_id=t, account_id=seeded.account_id)
            )
        # Aucune dette overflow, quel que soit le dépassement (budget peut être minuscule).
        assert await _overflow_set(s) == set()

    _run_scenario(overflow_prop_socle, sc, _body)


# ---------------------------------------------------------------------------
# Property 3 — `force_full_debt` : budget court-circuité + orientation + arrondi-0
# (AC #168 (3), ré-intitulée — review M1)
# ---------------------------------------------------------------------------


@given(sc=overflow_scenario_strategy(n_members=2, override="force_full_debt", with_budget=True))
@settings(max_examples=25, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_force_full_debt_budget_shortcircuit_property(
    overflow_prop_socle: str, sc: OverflowScenario
) -> None:
    s_payer = sc.payer_ratio
    s_other = sc.account.members[1].ratio  # = 1 − s_payer (Σ ratio == 1, 2 membres)

    async def _body(s: AsyncSession, seeded: _Seeded) -> None:
        debtor = seeded.member_ids[1]
        for t, txspec in zip(seeded.tx_ids, sc.txs, strict=True):
            await dispatch(
                s, TransactionConfirmedEvent(transaction_id=t, account_id=seeded.account_id)
            )
            # base = M (budget IGNORÉ bien que présent) ⇒ unique dette round(M × (1 − s_payer)).
            expected = (
                Money(txspec.amount_cents, "EUR").apply_ratio(Decimal(1) - s_payer).amount_cents
            )
            by_debtor = await _overflow_by_debtor(s, t)
            assert by_debtor == ({debtor: expected} if expected > 0 else {})
            # Orientation O→P + quote-part persistée (pas seulement le montant).
            rows = await s.execute(
                select(Debt.to_user_id, Debt.share_ratio).where(
                    Debt.origin == _OVERFLOW, Debt.source_transaction_id == t
                )
            )
            for to_user, share_ratio in rows.all():
                assert to_user == seeded.payer
                assert share_ratio == s_other

    _run_scenario(overflow_prop_socle, sc, _body)


# ---------------------------------------------------------------------------
# Property 4 — exclusivité d'origine (AC #168 additionnel, AC opposable #166 D2)
# ---------------------------------------------------------------------------


@given(sc=overflow_scenario_strategy(n_members=2, override="force_full_debt", with_budget=True))
@settings(max_examples=10, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_overflow_origin_exclusivity_property(
    overflow_prop_socle: str, sc: OverflowScenario
) -> None:
    # S1 — garantit qu'un overflow EST écrit sur la paire témoin (test non vacant).
    # Rejet négligeable : seul M × s_other < 0.5 est écarté (M ∈ [1, 1e7]).
    s_other = Decimal(1) - sc.payer_ratio
    expected = Money(sc.txs[0].amount_cents, "EUR").apply_ratio(s_other).amount_cents
    assume(expected > 0)

    async def _body(s: AsyncSession, seeded: _Seeded) -> None:
        tx0 = seeded.tx_ids[0]
        debtor = seeded.member_ids[1]

        # Sème la share_request témoin sur la MÊME paire (tx0, debtor → payer) qu'une
        # dette overflow ⇒ seul cas où le prédicat partiel uq_debts_overflow_active
        # sépare réellement les deux origines.
        def _sow(sync: Session) -> None:
            sync.add(
                Debt(
                    from_user_id=debtor,
                    to_user_id=seeded.payer,
                    amount_cents=777,
                    currency="EUR",
                    account_id=seeded.account_id,
                    source_transaction_id=tx0,
                    origin="personal_share_request",
                )
            )
            sync.flush()

        await s.run_sync(_sow)
        for t in seeded.tx_ids:
            await dispatch(
                s, TransactionConfirmedEvent(transaction_id=t, account_id=seeded.account_id)
            )
        # Ré-émet l'event de tx0 (stress upsert + prune sur la paire partagée).
        await dispatch(
            s, TransactionConfirmedEvent(transaction_id=tx0, account_id=seeded.account_id)
        )

        # Assertion-témoin : un overflow EST bien écrit sur la paire (sinon test vacant).
        assert _overflow_expected_on_pair(await _overflow_by_debtor(s, tx0), debtor, expected)
        # Invariant : la share_request témoin est INCHANGÉE (montant + origine).
        sr = (
            await s.execute(
                select(Debt).where(
                    Debt.source_transaction_id == tx0,
                    Debt.from_user_id == debtor,
                    Debt.to_user_id == seeded.payer,
                    Debt.origin == "personal_share_request",
                )
            )
        ).scalar_one()
        assert sr.amount_cents == 777  # noqa: PLR2004 — montant témoin
        assert sr.origin == "personal_share_request"

    _run_scenario(overflow_prop_socle, sc, _body)


def _overflow_expected_on_pair(by_debtor: dict[UUID, int], debtor: UUID, expected: int) -> bool:
    return by_debtor.get(debtor) == expected
