"""Service de création + lecture d'un règlement (S10.4).

`create_settlement` dérive les scalaires (montant viré via `transactions.public`,
contextes des dettes + `remaining` via S10.3), appelle le `SettlementValidator`
pur (S10.2), puis insère `Settlement` + N `SettlementLine` dans UNE transaction
DB. **Transaction-agnostic** : `flush()` mais JAMAIS `commit()` — la frontière
transactionnelle appartient à `get_db` (ADR 0015 — opération métier ordinaire :
insert indivisible, rollback voulu si échec ; gabarit `create_share_request`).

Anti-oracle (review #22) : toute dette/tx/règlement inaccessible ou inexistant →
**404 uniforme** (jamais 403, jamais d'echo d'id). Garde foyer effectful
(ADR 0011 §4) posée tôt (ii-bis), AVANT l'accessibilité user-level — l'isolation
foyer-level est « la porte la plus fondamentale ».

Taxonomie d'erreurs DB/accès (gabarit `ShareRequestError`), distincte de la
famille pure `SettlementValidationError` (`debts.domain`) que le boundary mappe
séparément. `code` (ClassVar) est le canal client stable et SANS PII — le
boundary ne recopie JAMAIS `str(exc)`.

N'importe que `debts.{domain,models,service}` (intra), `transactions.public`
(`get_transaction`, `TransactionState`, `is_transfer`) et `accounts.public`
(`HOUSEHOLD_ID`, `account_is_accessible`) — tous arcs déjà whitelistés (`2-debts`).
Le handle Core `table("accounts", …)` lit la table PEER par NOM, sans import
(mirror `dashboard._transactions`) ⇒ aucun nouvel arc import-linter.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Sequence
from typing import ClassVar
from uuid import UUID

from sqlalchemy import column, select, table
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.accounts.public import HOUSEHOLD_ID, account_is_accessible
from backend.modules.debts.domain import (
    DebtContext,
    SettlementLineInput,
    SettlementType,
    SettlementValidator,
)
from backend.modules.debts.models import Debt, Settlement, SettlementLine
from backend.modules.debts.service.remaining import compute_remaining
from backend.modules.transactions.public import (
    TransactionState,
    get_transaction,
    is_transfer,
)

# Handle Core sur la table PEER `accounts` (gabarit `dashboard._transactions`) :
# résout `account_id → household_id` SANS import (aucun arc import-linter).
_accounts = table("accounts", column("id"), column("household_id"))


class SettlementServiceError(Exception):
    """Base des rejets d'accès/état d'un règlement (gabarit `ShareRequestError`).

    Base commune ⇒ le boundary mappe TOUTE la famille avec un seul
    `except SettlementServiceError`. `code` est stable et SANS PII (recopié tel
    quel au client ; JAMAIS `str(exc)`).
    """

    code: ClassVar[str] = "settlement_service_error"


class SettlementDebtNotAccessibleError(SettlementServiceError):
    """Une dette ciblée est inexistante OU le caller n'en est pas partie OU elle
    résout à un autre foyer → **404 UNIFORME** (anti-oracle). Sous-cas distingués
    par des `code` pour le log, MÊME réponse 404."""

    code: ClassVar[str] = "settlement_debt_not_accessible"


class CrossHouseholdError(SettlementDebtNotAccessibleError):
    """Sous-cas foyer (ADR 0011 §4) : un `debt_id`/`linked_transaction_id` résout
    à un autre foyer que le `Settlement`. `code` distinct pour l'observabilité ;
    réponse 404 identique (hérite du détail uniforme)."""

    code: ClassVar[str] = "cross_household_leak"


class LinkedTransactionNotAccessibleError(SettlementServiceError):
    """Tx liée inexistante OU inaccessible au caller → 404 uniforme."""

    code: ClassVar[str] = "linked_transaction_not_accessible"


class LinkedTransactionNotConfirmedError(SettlementServiceError):
    """Tx liée non `confirmed` (ADR 0001, montant gelé) → 422."""

    code: ClassVar[str] = "linked_transaction_not_confirmed"


class LinkedTransactionNotTransferError(SettlementServiceError):
    """`internal_transfer` dont la tx liée n'est pas un virement (≥2 comptes) → 422."""

    code: ClassVar[str] = "linked_transaction_not_transfer"


def _assert_single_household(household_ids: set[UUID], *, expected: UUID) -> None:
    """PUR : lève `CrossHouseholdError` si un id diffère de `expected` (D4).

    Isolé pour être testable unitairement (la branche de rejet n'est PAS
    constructible en intégration sous le singleton ADR 0010 — cf. plan §6 ;
    exercée sur le chemin réel via monkeypatch de `_resolve_households`).
    """
    if any(h != expected for h in household_ids):
        raise CrossHouseholdError


async def _resolve_households(session: AsyncSession, account_ids: set[UUID]) -> set[UUID]:
    """`account_id → household_id` via le handle Core `accounts` (aucun import)."""
    if not account_ids:
        return set()
    rows = await session.execute(
        select(_accounts.c.household_id).where(_accounts.c.id.in_(account_ids))
    )
    return {r[0] for r in rows}


def derive_transfer_amount(split_amounts_cents: Sequence[int]) -> int:
    """PUR (D3) : magnitude du mouvement = Σ des splits POSITIFS.

    Une tx `confirmed` est zero-sum (ADR 0001) ⇒ Σ positifs == abs(Σ négatifs).
    Extrait en fonction pure pour être couvert en property-based (Hypothesis,
    T-M3) indépendamment de l'effet de bord du service.
    """
    return sum(a for a in split_amounts_cents if a > 0)


async def create_settlement(  # noqa: PLR0913 — paramètres d'acte keyword-only
    session: AsyncSession,
    *,
    settlement_type: SettlementType,
    linked_transaction_id: UUID | None,
    settled_at: dt.date,
    note: str | None,
    lines: Sequence[SettlementLineInput],
    by_user_id: UUID,
) -> Settlement:
    """Valide + insère `Settlement` + N `SettlementLine` (UNE transaction DB).

    Ordre des vérifs (404 d'abord, anti-oracle, gabarit S09.3 ; garde foyer AVANT
    l'accessibilité user-level — S-M2/ADR 0011 §4) :
    (i)     chaque `debt_id` des lignes EXISTE (charge les `Debt`) → sinon 404 ;
    (ii)    `by_user_id` partie (`from` OU `to`) de CHAQUE dette → sinon 404 ;
    (ii-a)  si non-virtuel : tx liée EXISTE (`linked_transaction_id` NOT NULL &
            `get_transaction` non None) → sinon 404 (existence requise pour
            résoudre ses comptes ; même 404 uniforme, anti-oracle) ;
    (ii-bis) 🔒 ISOLATION FOYER (ADR 0011 §4, porte la PLUS fondamentale, AVANT le
            user-level) : tous les `account_id` des dettes ET (si non-virtuel)
            `tx.account_id` + `{s.account_id}` résolvent au `household_id` du
            `Settlement` (= `HOUSEHOLD_ID`) → sinon 404 ;
    (iii)   si non-virtuel : tx accessible au caller sur TOUS ses comptes → sinon
            404 ; tx `confirmed` → sinon 422 ; pour `internal_transfer`,
            `is_transfer(tx)` → sinon 422 ;
    (iv)    `linked_transaction_amount_cents = derive_transfer_amount(...)` (None si virtual) ;
    (v)     dérive les `DebtContext` (contreparties + devise + `remaining` S10.3) ;
    (vi)    `SettlementValidator.validate(...)` → lève `SettlementValidationError` (→ 422) ;
    (vii)   insert `Settlement` + N `SettlementLine` (MÊME transaction ; flush, pas commit).
    """
    # (i) dettes existantes → 404 uniforme
    debt_ids = [ln.debt_id for ln in lines]
    debts = list(
        (await session.execute(select(Debt).where(Debt.id.in_(debt_ids)))).scalars().all()
    )
    by_id = {d.id: d for d in debts}
    if any(did not in by_id for did in debt_ids):
        raise SettlementDebtNotAccessibleError

    # (ii) caller partie de CHAQUE dette (RBAC user-level) → 404 uniforme
    if any(by_user_id not in (d.from_user_id, d.to_user_id) for d in debts):
        raise SettlementDebtNotAccessibleError

    # (ii-a) EXISTENCE de la tx liée (requise pour ii-bis ; 404 uniforme)
    tx = None
    if settlement_type != "virtual":
        tx = (
            await get_transaction(session, tx_id=linked_transaction_id)
            if linked_transaction_id is not None
            else None
        )
        if tx is None:
            raise LinkedTransactionNotAccessibleError

    # (ii-bis) 🔒 GARDE FOYER (AVANT le user-level — S-M2/S-M3) : comptes des
    # dettes + tx.account_id (racine) + comptes des splits → HOUSEHOLD_ID.
    account_ids = {d.account_id for d in debts}
    if tx is not None:
        account_ids.add(tx.account_id)  # S-M3 : racine incluse
        account_ids |= {s.account_id for s in tx.splits}
    _assert_single_household(
        await _resolve_households(session, account_ids), expected=HOUSEHOLD_ID
    )

    # (iii) accessibilité user-level + état/forme de la tx liée (non-virtuel)
    linked_amount: int | None = None
    if settlement_type != "virtual":
        assert tx is not None  # garanti par (ii-a)
        # A-m1 : accessibilité sur TOUS les comptes du virement (≥2 pour un
        # internal_transfer), pas le seul `tx.account_id`. Sous singleton V1 tout
        # compte du foyer est accessible ; la boucle évite une assomption cachée.
        tx_account_ids = {tx.account_id} | {s.account_id for s in tx.splits}
        for acc_id in tx_account_ids:
            if not await account_is_accessible(session, account_id=acc_id, user_id=by_user_id):
                raise LinkedTransactionNotAccessibleError
        if tx.state is not TransactionState.CONFIRMED:
            raise LinkedTransactionNotConfirmedError
        if settlement_type == "internal_transfer" and not is_transfer(tx):
            raise LinkedTransactionNotTransferError
        # (iv) montant viré = Σ splits positifs (helper pur, property-tested T-M3)
        linked_amount = derive_transfer_amount([s.amount.amount_cents for s in tx.splits])

    # (v) DebtContext (remaining COURANT via S10.3, avant ce règlement)
    debt_contexts = {
        d.id: DebtContext(
            debt_id=d.id,
            from_user_id=d.from_user_id,
            to_user_id=d.to_user_id,
            currency=d.currency,  # type: ignore[arg-type]  # projection serveur validée (A-m2)
            remaining_cents=await compute_remaining(session, debt_id=d.id),
        )
        for d in debts
    }

    # (vi) validateur pur (lève SettlementValidationError → 422 au boundary)
    SettlementValidator.validate(
        settlement_type=settlement_type,
        lines=lines,
        debt_contexts=debt_contexts,
        linked_transaction_amount_cents=linked_amount,
    )

    # (vii) insert Settlement + lignes (MÊME transaction ; commit par get_db)
    settlement = Settlement(
        household_id=HOUSEHOLD_ID,
        created_by=by_user_id,
        type=settlement_type,
        linked_transaction_id=linked_transaction_id,
        settled_at=settled_at,
        note=note,
    )
    session.add(settlement)
    await session.flush()  # PK settlement disponible pour les FK des lignes
    for ln in lines:
        session.add(
            SettlementLine(
                settlement_id=settlement.id,
                debt_id=ln.debt_id,
                amount_cents=ln.amount_cents,
                currency=debt_contexts[ln.debt_id].currency,  # devise de la Debt (cohérence DB)
            )
        )
    await session.flush()
    return settlement
