"""Helpers d'intégration partagés du module `debts` (S09.3 + S09.5).

Extraits de `test_share_request_service.py` (review S09.5 m3) pour que
`test_debts_invariants.py` les consomme sans importer un symbole privé d'un
module de test (couplage test→test + `reportPrivateUsage`). Module NON collecté
(pas de préfixe `test_`, précédent `tests/e2e/_helpers.py`), hors `root_package`
import-linter. Aucun comportement modifié : mêmes corps, noms rendus publics
(`seed` ex-`_seed`, `Scenario` ex-`_Scenario`, `debt_count` ex-`_debt_count`),
plus `share_request_count` (nouveau, typé) pour le consommateur S09.5.

S10.3 ajoute `settle_debt`/`debt_id_between` (seed d'un `Settlement` virtuel +
`SettlementLine`), factorisés depuis `test_debts_dashboard_service.py` et
`test_debts_routes.py` (review S10.3 — un seul corps à maintenir au lieu de deux
copies). Aucun service `create_settlement` n'existe encore (S10.4) : la ligne est
insérée directement, ce qui suffit au chemin de lecture S10.3.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session

from backend.modules.accounts.models import AccountMember
from backend.modules.debts.models import Debt, Settlement, SettlementLine, ShareRequest
from tests.factories.sqlalchemy import (
    AccountFactory,
    CategoryFactory,
    SplitFactory,
    TransactionFactory,
    UserFactory,
)


def run_hypothesis_db_example[Seeded](
    url: str,
    seed_sync: Callable[[Session], Seeded],
    body: Callable[[AsyncSession, Seeded], Awaitable[None]],
) -> None:
    """Engine + session par exemple Hypothesis (gabarit D15 S11.3) : un nouvel
    `engine` → `begin` → `seed_sync` (dans `run_sync`) → `body` → `rollback` → `dispose`.

    Le moteur neuf par exemple évite les soucis d'event-loop avec Hypothesis ; le
    `rollback` + `dispose` garantissent l'isolation inter-exemples (rien ne persiste).
    Factorisé depuis le `_run_scenario` de la suite property overflow S11.5 pour que
    toute suite « Hypothesis sur DB » (schéma `create_all` module-scoped + seed/assert
    par exemple) réutilise un seul corps. Fonction synchrone (les tests `@given` le
    sont) : elle pilote elle-même la boucle via `asyncio.run`.
    """

    async def _run() -> None:
        engine = create_async_engine(url)
        try:
            sm = async_sessionmaker(engine, expire_on_commit=False)
            async with sm() as s:
                await s.begin()
                seeded = await s.run_sync(seed_sync)
                await body(s, seeded)
                await s.rollback()
        finally:
            await engine.dispose()

    asyncio.run(_run())


# Precise mirror of `bound_transaction_factories`'s return (conftest.py): the
# bundle yields the four bound factory CLASSES in order user/account/tx/split.
TxFactoryBundle = Callable[
    [],
    Awaitable[
        tuple[type[UserFactory], type[AccountFactory], type[TransactionFactory], type[SplitFactory]]
    ],
]

# (amount_cents, is_classification) — a classification leg carries a category,
# a funding leg does not (leg_role derived by the ORM default). Legs must sum to
# zero for a `confirmed` tx (the domain re-checks zero-sum on read).
Leg = tuple[int, bool]


@dataclass
class Scenario:
    alice_id: uuid.UUID  # owner of the personal account = creditor
    bob_id: uuid.UUID  # active foyer member = debtor
    account_id: uuid.UUID
    tx_id: uuid.UUID


async def seed(  # noqa: PLR0913 — keyword-only scenario knobs
    session: AsyncSession,
    factories: TxFactoryBundle,
    *,
    legs: list[Leg],
    state: str = "confirmed",
    personal: bool = True,
    tx_owner_is_alice: bool = True,
    bob_disabled: bool = False,
) -> Scenario:
    """Seed Alice (owner/creditor), Bob (debtor) + a tx with the given legs.

    Defaults (all knobs off) yield the happy-path scenario consumed by S09.5's
    real-flow CASCADE test. The optional knobs drive the authz scenarios of the
    S09.3 service suite: `personal=False` builds a *shared* account (owner NULL)
    with Alice as member (accessible but not owned-personal → vérif ii);
    `tx_owner_is_alice=False` puts the tx on a third user's personal account
    (inaccessible to Alice → vérif i); `bob_disabled=True` disables Bob
    (F02 → vérif iv).
    """
    user_factory, account_factory, tx_factory, split_factory = await factories()

    def _do(sync_session: Session) -> Scenario:
        alice = user_factory(email="alice@example.com")
        bob_kwargs: dict[str, object] = {"email": "bob@example.com"}
        if bob_disabled:
            bob_kwargs["disabled_at"] = dt.datetime(2026, 1, 1, tzinfo=dt.UTC)
        bob = user_factory(**bob_kwargs)

        if not tx_owner_is_alice:
            carol = user_factory(email="carol@example.com")
            account = account_factory(owner_id=carol.id, name="Carol perso")
            tx_creator = carol.id
        elif personal:
            account = account_factory(owner_id=alice.id, name="Alice perso")
            tx_creator = alice.id
        else:  # shared account: owner NULL + Alice as member
            account = account_factory(owner_id=None, name="Commun")
            sync_session.add(
                AccountMember(
                    account_id=account.id,
                    user_id=alice.id,
                    default_share_ratio=Decimal("1.0"),
                )
            )
            sync_session.flush()
            tx_creator = alice.id

        tx = tx_factory(account_id=account.id, created_by=tx_creator, state=state, splits=False)
        for amount, is_classification in legs:
            category_id = CategoryFactory().id if is_classification else None
            split_factory(
                transaction_id=tx.id,
                account_id=account.id,
                amount_cents=amount,
                currency="EUR",
                category_id=category_id,
            )
        return Scenario(alice.id, bob.id, account.id, tx.id)

    return await session.run_sync(_do)


async def debt_count(session: AsyncSession, *, tx_id: uuid.UUID) -> int:
    stmt = select(func.count()).select_from(Debt).where(Debt.source_transaction_id == tx_id)
    return int((await session.execute(stmt)).scalar_one())


async def share_request_count(session: AsyncSession, *, tx_id: uuid.UUID) -> int:
    stmt = (
        select(func.count())
        .select_from(ShareRequest)
        .where(ShareRequest.source_transaction_id == tx_id)
    )
    return int((await session.execute(stmt)).scalar_one())


# Singleton household FK target seeded by the `household_singleton` fixture
# (ADR 0010) — every `Settlement` row scopes to it.
HOUSEHOLD_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


async def debt_id_between(
    session: AsyncSession, *, debtor_id: uuid.UUID, creditor_id: uuid.UUID
) -> uuid.UUID:
    """The materialised debt id for a (debtor → creditor) pair."""
    return (
        await session.execute(
            select(Debt.id).where(Debt.from_user_id == debtor_id, Debt.to_user_id == creditor_id)
        )
    ).scalar_one()


async def settle_debt(
    session: AsyncSession, *, debt_id: uuid.UUID, amount_cents: int, created_by: uuid.UUID
) -> None:
    """Insert a virtual `Settlement` + one `SettlementLine` apurant `debt_id`.

    No `create_settlement` service exists yet (S10.4) — the line is inserted
    directly, which is all the S10.3 read path needs. The `virtual` type keeps
    the seed self-contained (no linked transaction): the remaining formula is
    orthogonal to the settlement `type`.
    """

    def _do(s: Session) -> None:
        settlement = Settlement(
            household_id=HOUSEHOLD_ID,
            created_by=created_by,
            type="virtual",
            linked_transaction_id=None,
            settled_at=dt.date(2026, 6, 3),
        )
        s.add(settlement)
        s.flush()
        s.add(
            SettlementLine(
                settlement_id=settlement.id,
                debt_id=debt_id,
                amount_cents=amount_cents,
                currency="EUR",
            )
        )
        s.flush()

    await session.run_sync(_do)
