"""Example-based d'intégration : conservation persistée + over-settlement + CASCADE (S10.5).

Les invariants PERSISTÉS du règlement (round-trip DB) sont couverts ICI en
example-based (testcontainers), JAMAIS sous Hypothesis : le property-based sur
effets de bord est flaky (`Stratégie de tests` §12). Les properties pures vivent
dans `tests/unit/test_settlement_invariants.py`.

Delta explicite vs les suites existantes (anti-redondance, plan D6) :
- `test_create_settlement.py` (S10.4) — happy 2-dettes symétriques (apurement
  TOTAL), propagation `OverSettlementError` (n'asserte QUE l'exception) ;
- `test_settlement_models.py` (S10.1) — CASCADE au NIVEAU des lignes, sur des
  rows construites à la main (pas via `create_settlement`).

Ici : (1) conservation sur un scénario réellement PARTIEL cross-direction +
dette témoin, assertée DETTE-PAR-DETTE via `compute_remaining` (NON filtré : seul
oracle valable — `list_open_debts_between` exclut les dettes soldées ⇒ une somme
y serait tautologique) ; (2) over-settlement réel → ZÉRO `Settlement`/`SettlementLine` ;
(3) CASCADE `Settlement`→lignes faisant REMONTER `remaining` au montant plein
(dette rouverte) + CASCADE `Debt`→lignes après un flux `create_settlement` RÉEL.

Seed gabarit copié inline depuis `test_create_settlement.py` (`_make_account` /
`_make_external_tx` / `_make_debt` / `_line`). Pas de `HOUSEHOLD_ID` ici : le flux
`create_settlement` scope lui-même la row `Settlement` au foyer singleton (≠
`test_settlement_models.py`, qui construit les rows à la main). L'extraction des
`_make_*` dans `_debts_helpers.py` reste un follow-up DRY (plan §6).
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Awaitable, Callable

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.accounts.domain import AccountType
from backend.modules.accounts.models import Account
from backend.modules.auth.models import User
from backend.modules.debts.domain import OverSettlementError, SettlementLineInput
from backend.modules.debts.models import Debt, Settlement, SettlementLine
from backend.modules.debts.public import compute_remaining, create_settlement
from backend.modules.transactions.models import Split, Transaction

pytestmark = pytest.mark.usefixtures("household_singleton")

UserFactory = Callable[..., Awaitable[User]]


async def _make_account(session: AsyncSession, owner_id: uuid.UUID) -> uuid.UUID:
    account = Account(
        name="Compte courant", type=AccountType.COURANT, currency="EUR", owner_id=owner_id
    )
    session.add(account)
    await session.flush()
    return account.id


async def _make_external_tx(
    session: AsyncSession, *, account_id: uuid.UUID, created_by: uuid.UUID, amount_cents: int
) -> uuid.UUID:
    """Tx confirmée sur un SEUL compte : funding(−amount)+funding(+amount).

    `derive_transfer_amount` → amount (Σ splits positifs) ; un `external_transfer`
    n'exige PAS `is_transfer` (gabarit `test_create_settlement.py`).
    """
    tx = Transaction(
        account_id=account_id, date=dt.date(2026, 6, 1), state="confirmed", created_by=created_by
    )
    session.add(tx)
    await session.flush()
    for amount in (-amount_cents, amount_cents):
        session.add(
            Split(
                transaction_id=tx.id,
                account_id=account_id,
                amount_cents=amount,
                currency="EUR",
                leg_role="funding",
            )
        )
    await session.flush()
    return tx.id


async def _make_debt(  # noqa: PLR0913 — keyword-only seed helper
    session: AsyncSession,
    *,
    from_user_id: uuid.UUID,
    to_user_id: uuid.UUID,
    account_id: uuid.UUID,
    source_transaction_id: uuid.UUID,
    amount_cents: int,
) -> Debt:
    debt = Debt(
        from_user_id=from_user_id,
        to_user_id=to_user_id,
        amount_cents=amount_cents,
        currency="EUR",
        account_id=account_id,
        source_transaction_id=source_transaction_id,
        origin="personal_share_request",
    )
    session.add(debt)
    await session.flush()
    return debt


def _line(debt_id: uuid.UUID, amount_cents: int) -> SettlementLineInput:
    return SettlementLineInput(debt_id=debt_id, amount_cents=amount_cents)


async def _settlement_count(session: AsyncSession) -> int:
    return int((await session.execute(select(func.count()).select_from(Settlement))).scalar_one())


async def _line_count(session: AsyncSession) -> int:
    return int(
        (await session.execute(select(func.count()).select_from(SettlementLine))).scalar_one()
    )


# ---------------------------------------------------------------------------
# (1) Conservation persistée — scénario PARTIEL cross-direction + dette témoin
# ---------------------------------------------------------------------------


async def test_conservation_persisted_partial_cross_direction(
    household_singleton: AsyncSession, bound_user_factory: UserFactory
) -> None:
    # DELTA vs test_virtual_success_cross_direction_nets_to_zero (apurement TOTAL
    # symétrique) : scénario réellement PARTIEL (lignes < remaining) cross-direction
    # à net 0 + une 3e dette TÉMOIN non touchée. Conservation assertée DETTE-PAR-DETTE
    # via compute_remaining (NON filtré) sur des restants NON triviaux (3000) — pas
    # sum(list_open_debts_between)==0 (liste vide après apurement ⇒ tautologie).
    alice, bob = await bound_user_factory(), await bound_user_factory()
    acc = await _make_account(household_singleton, alice.id)
    tx_id = await _make_external_tx(
        household_singleton, account_id=acc, created_by=alice.id, amount_cents=1
    )
    a_to_b = await _make_debt(
        household_singleton,
        from_user_id=alice.id,
        to_user_id=bob.id,
        account_id=acc,
        source_transaction_id=tx_id,
        amount_cents=5000,
    )
    b_to_a = await _make_debt(
        household_singleton,
        from_user_id=bob.id,
        to_user_id=alice.id,
        account_id=acc,
        source_transaction_id=tx_id,
        amount_cents=5000,
    )
    witness = await _make_debt(  # même direction qu'a_to_b, JAMAIS apurée
        household_singleton,
        from_user_id=alice.id,
        to_user_id=bob.id,
        account_id=acc,
        source_transaction_id=tx_id,
        amount_cents=3000,
    )

    # virtual exige net 0 ⇒ on apure la MÊME magnitude (2000) dans les deux sens : PARTIEL.
    await create_settlement(
        household_singleton,
        settlement_type="virtual",
        linked_transaction_id=None,
        settled_at=dt.date(2026, 6, 3),
        note=None,
        lines=[_line(a_to_b.id, 2000), _line(b_to_a.id, 2000)],
        by_user_id=alice.id,
    )

    # Conservation : chaque restant apuré = 5000 − 2000 = 3000 (NON trivial), la 3e
    # dette reste à son plein montant. compute_remaining NE filtre PAS → vrai oracle.
    assert await compute_remaining(household_singleton, debt_id=a_to_b.id) == 3000
    assert await compute_remaining(household_singleton, debt_id=b_to_a.id) == 3000
    assert await compute_remaining(household_singleton, debt_id=witness.id) == 3000
    # Net orienté du restant sur la PAIRE {alice, bob} INCHANGÉ par un règlement
    # virtual (3000 a→b − 3000 b→a == 0 avant ET après) : conservation du solde net.


# ---------------------------------------------------------------------------
# (2) Over-settlement réel → aucun effet persisté (rejet PRÉ-INSERT)
# ---------------------------------------------------------------------------


async def test_over_settlement_persists_nothing(
    household_singleton: AsyncSession, bound_user_factory: UserFactory
) -> None:
    # DELTA vs test_over_settlement_propagates (n'asserte QUE l'exception) : ici on
    # asserte qu'AUCUN effet n'est persisté (0 Settlement, 0 SettlementLine). NB :
    # create_settlement valide AVANT tout session.add (rejet PRÉ-INSERT, règle (7)
    # du validateur) ⇒ « 0 ligne » découle du rejet en amont, PAS d'un rollback
    # d'insertion partielle (atomicité multi-ligne post-flush hors scope, plan §6).
    debtor, creditor = await bound_user_factory(), await bound_user_factory()
    acc = await _make_account(household_singleton, creditor.id)
    tx_id = await _make_external_tx(
        household_singleton, account_id=acc, created_by=creditor.id, amount_cents=1
    )
    debt = await _make_debt(
        household_singleton,
        from_user_id=debtor.id,
        to_user_id=creditor.id,
        account_id=acc,
        source_transaction_id=tx_id,
        amount_cents=5000,
    )
    before = await _settlement_count(household_singleton)

    with pytest.raises(OverSettlementError):
        await create_settlement(
            household_singleton,
            settlement_type="virtual",
            linked_transaction_id=None,
            settled_at=dt.date(2026, 6, 3),
            note=None,
            lines=[_line(debt.id, 8000)],  # > remaining 5000
            by_user_id=creditor.id,
        )

    assert await _settlement_count(household_singleton) == before  # aucun Settlement
    assert await _line_count(household_singleton) == 0  # aucune SettlementLine


# ---------------------------------------------------------------------------
# (3) CASCADE — Settlement→lignes (remaining remonte) + Debt→lignes (flux réel)
# ---------------------------------------------------------------------------


async def test_cascade_settlement_reopens_debt(
    household_singleton: AsyncSession, bound_user_factory: UserFactory
) -> None:
    # DELTA vs test_delete_settlement_cascades_lines (compte les lignes au NIVEAU
    # modèle) : ici on lie le CASCADE à la FORMULE remaining — supprimer le
    # Settlement fait REMONTER remaining au montant plein (la dette redevient
    # ouverte). Flux create_settlement RÉEL (external_transfer apurant 5000).
    debtor, creditor = await bound_user_factory(), await bound_user_factory()
    acc = await _make_account(household_singleton, creditor.id)
    tx_id = await _make_external_tx(
        household_singleton, account_id=acc, created_by=creditor.id, amount_cents=5000
    )
    debt = await _make_debt(
        household_singleton,
        from_user_id=debtor.id,
        to_user_id=creditor.id,
        account_id=acc,
        source_transaction_id=tx_id,
        amount_cents=5000,
    )
    s = await create_settlement(
        household_singleton,
        settlement_type="external_transfer",
        linked_transaction_id=tx_id,
        settled_at=dt.date(2026, 6, 3),
        note=None,
        lines=[_line(debt.id, 5000)],
        by_user_id=creditor.id,
    )
    assert await compute_remaining(household_singleton, debt_id=debt.id) == 0  # apurée

    await household_singleton.delete(await household_singleton.get(Settlement, s.id))
    await household_singleton.flush()

    # remaining REMONTE au montant plein : la dette redevient ouverte (lignes CASCADÉES).
    assert await compute_remaining(household_singleton, debt_id=debt.id) == 5000


async def test_cascade_debt_removes_lines(
    household_singleton: AsyncSession, bound_user_factory: UserFactory
) -> None:
    # CASCADE debt → settlement_lines APRÈS un create_settlement RÉEL (vs rows
    # construites à la main en S10.1) : supprimer la Debt nettoie ses lignes.
    debtor, creditor = await bound_user_factory(), await bound_user_factory()
    acc = await _make_account(household_singleton, creditor.id)
    tx_id = await _make_external_tx(
        household_singleton, account_id=acc, created_by=creditor.id, amount_cents=5000
    )
    debt = await _make_debt(
        household_singleton,
        from_user_id=debtor.id,
        to_user_id=creditor.id,
        account_id=acc,
        source_transaction_id=tx_id,
        amount_cents=5000,
    )
    await create_settlement(
        household_singleton,
        settlement_type="external_transfer",
        linked_transaction_id=tx_id,
        settled_at=dt.date(2026, 6, 3),
        note=None,
        lines=[_line(debt.id, 5000)],
        by_user_id=creditor.id,
    )
    assert await _line_count(household_singleton) == 1

    await household_singleton.delete(await household_singleton.get(Debt, debt.id))
    await household_singleton.flush()

    assert await _line_count(household_singleton) == 0  # lignes CASCADÉES par la Debt
