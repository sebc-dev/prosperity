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
from typing import ClassVar, Protocol
from uuid import UUID

from sqlalchemy import and_, column, or_, select, table
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.accounts.public import HOUSEHOLD_ID, account_is_accessible
from backend.modules.debts.domain import (
    DebtContext,
    SettlementLineInput,
    SettlementType,
    SettlementValidator,
)
from backend.modules.debts.models import Debt, Settlement, SettlementLine
from backend.modules.debts.service.dashboard import DebtWithContext, project_debts_by_ids
from backend.modules.debts.service.remaining import compute_remaining_for_debts
from backend.modules.transactions.public import (
    TransactionState,
    get_transaction,
    is_transfer,
)
from backend.shared.money import Money

# Handle Core sur la table PEER `accounts` (gabarit `dashboard._transactions`) :
# résout `account_id → household_id` SANS import (aucun arc import-linter).
_accounts = table("accounts", column("id"), column("household_id"))


class _LinkedTransactionSplit(Protocol):
    """Duck-typing surface d'un split de la tx liée — PUREMENT STATIQUE (aucun
    import `transactions.domain`, contrat `2-debts`, gabarit
    `overflow_materializer._OverflowSplit`)."""

    @property
    def account_id(self) -> UUID: ...
    @property
    def amount(self) -> Money: ...


class _LinkedTransaction(Protocol):
    """Duck-typing surface de la tx liée que `create_settlement` dérive
    (gabarit `overflow_materializer._OverflowTx`) : la concrète
    `transactions.domain.Transaction` la satisfait structurellement, sans que
    `debts` ne nomme jamais cet interne (`2-debts`)."""

    @property
    def account_id(self) -> UUID: ...
    @property
    def splits(self) -> Sequence[_LinkedTransactionSplit]: ...
    @property
    def state(self) -> TransactionState: ...


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


async def _load_targeted_debts(session: AsyncSession, debt_ids: Sequence[UUID]) -> list[Debt]:
    """Étape (i) de `create_settlement` : charge les `Debt` ciblées.

    Chaque `debt_id` des lignes doit EXISTER → sinon 404 uniforme (anti-oracle).
    """
    debts = list((await session.execute(select(Debt).where(Debt.id.in_(debt_ids)))).scalars().all())
    by_id = {d.id: d for d in debts}
    if any(did not in by_id for did in debt_ids):
        raise SettlementDebtNotAccessibleError
    return debts


async def _load_linked_transaction(
    session: AsyncSession, *, settlement_type: SettlementType, linked_transaction_id: UUID | None
):
    """Étape (ii-a) de `create_settlement` : EXISTENCE de la tx liée (requise
    pour la garde foyer ii-bis ; `None` si `virtual`) → sinon 404 uniforme.

    PAS d'annotation de retour explicite (volontaire) : le type réel inféré
    (`transactions.domain.Transaction | None`) reste un INTERNE du module
    `transactions` (forbidden par le contrat `2-debts`) — le nommer ici
    exigerait un import direct interdit. L'appelant (`create_settlement`)
    récupère cette valeur dans une variable LOCALE (non un paramètre : aucune
    annotation requise par pyright strict) qui garde ce type nominal inféré,
    ré-utilisable avec `is_transfer` (signature nominale) ; les autres helpers
    qui REÇOIVENT cette tx en PARAMÈTRE la typent via le Protocol structurel
    `_LinkedTransaction` (satisfait structurellement, sans jamais nommer
    l'interne)."""
    if settlement_type == "virtual":
        return None
    tx = (
        await get_transaction(session, tx_id=linked_transaction_id)
        if linked_transaction_id is not None
        else None
    )
    if tx is None:
        raise LinkedTransactionNotAccessibleError
    return tx


async def _assert_household_isolation(
    session: AsyncSession, debts: Sequence[Debt], tx: _LinkedTransaction | None
) -> None:
    """Étape (ii-bis) de `create_settlement` : 🔒 GARDE FOYER (AVANT le
    user-level — S-M2/S-M3), la porte la PLUS fondamentale (ADR 0011 §4).

    Comptes des dettes + `tx.account_id` (racine) + comptes des splits doivent
    tous résoudre au `household_id` du `Settlement` (= `HOUSEHOLD_ID`).
    """
    account_ids = {d.account_id for d in debts}
    if tx is not None:
        account_ids.add(tx.account_id)  # S-M3 : racine incluse
        account_ids |= {s.account_id for s in tx.splits}
    _assert_single_household(await _resolve_households(session, account_ids), expected=HOUSEHOLD_ID)


async def _validate_linked_transaction(
    session: AsyncSession,
    tx: _LinkedTransaction | None,
    *,
    settlement_type: SettlementType,
    by_user_id: UUID,
    is_actual_transfer: bool,
) -> int | None:
    """Étapes (iii)/(iv) de `create_settlement` : accessibilité user-level +
    état/forme de la tx liée, puis montant viré (`None` si `virtual`).

    Accessible au caller sur TOUS ses comptes → sinon 404 ; `confirmed` →
    sinon 422 ; pour `internal_transfer`, `is_actual_transfer` (== `is_transfer(tx)`,
    calculé par l'appelant SUR LE TYPE NOMINAL — `tx` est ici le Protocol
    structurel `_LinkedTransaction`, insuffisant pour la signature nominale
    d'`is_transfer`) → sinon 422 ; `linked_transaction_amount_cents =
    derive_transfer_amount(...)`.
    """
    if settlement_type == "virtual":
        return None
    assert tx is not None  # garanti par (ii-a) / `_load_linked_transaction`
    # A-m1 : accessibilité sur TOUS les comptes du virement (≥2 pour un
    # internal_transfer), pas le seul `tx.account_id`. Sous singleton V1 tout
    # compte du foyer est accessible ; la boucle évite une assomption cachée.
    tx_account_ids = {tx.account_id} | {s.account_id for s in tx.splits}
    for acc_id in tx_account_ids:
        if not await account_is_accessible(session, account_id=acc_id, user_id=by_user_id):
            raise LinkedTransactionNotAccessibleError
    if tx.state is not TransactionState.CONFIRMED:
        raise LinkedTransactionNotConfirmedError
    if settlement_type == "internal_transfer" and not is_actual_transfer:
        raise LinkedTransactionNotTransferError
    # (iv) montant viré = Σ splits positifs (helper pur, property-tested T-M3)
    return derive_transfer_amount([s.amount.amount_cents for s in tx.splits])


async def _build_debt_contexts(
    session: AsyncSession, debts: Sequence[Debt]
) -> dict[UUID, DebtContext]:
    """Étape (v) de `create_settlement` : dérive les `DebtContext` (remaining
    COURANT via S10.3, avant ce règlement).

    Le restant des N dettes est batché en UNE requête (pas un N+1
    `compute_remaining` par dette) ; toutes existent (prouvé en (i)) ⇒ chaque
    `d.id` est dans le dict.
    """
    remaining_by_id = await compute_remaining_for_debts(session, debt_ids=[d.id for d in debts])
    return {
        d.id: DebtContext(
            debt_id=d.id,
            from_user_id=d.from_user_id,
            to_user_id=d.to_user_id,
            currency=d.currency,  # type: ignore[arg-type]  # projection serveur validée (A-m2)
            remaining_cents=remaining_by_id[d.id],
        )
        for d in debts
    }


async def _persist_settlement_lines(
    session: AsyncSession,
    settlement: Settlement,
    lines: Sequence[SettlementLineInput],
    debt_contexts: dict[UUID, DebtContext],
) -> None:
    """Fin de l'étape (vii) de `create_settlement` : insère les N
    `SettlementLine` liées à `settlement` (déjà flush pour sa PK) — MÊME
    transaction ; flush, pas commit (`get_db`)."""
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

    Chaque étape est déléguée à une fonction privée dédiée (`_load_*` /
    `_assert_*` / `_validate_*` / `_build_*` / `_persist_settlement_lines`),
    appelée dans le MÊME ORDRE que ci-dessus (C901) — cette fonction reste une
    simple composition séquentielle.
    """
    debt_ids = [ln.debt_id for ln in lines]
    debts = await _load_targeted_debts(session, debt_ids)

    # (ii) caller partie de CHAQUE dette (RBAC user-level) → 404 uniforme
    if any(by_user_id not in (d.from_user_id, d.to_user_id) for d in debts):
        raise SettlementDebtNotAccessibleError

    tx = await _load_linked_transaction(
        session, settlement_type=settlement_type, linked_transaction_id=linked_transaction_id
    )
    # `is_transfer` a une signature NOMINALE (`transactions.domain.Transaction`) :
    # calculée ICI, tant que `tx` porte encore son type inféré réel (variable
    # locale, pas un paramètre — aucune annotation Protocol requise), avant
    # d'être passée en aval sous le Protocol structurel `_LinkedTransaction`.
    is_actual_transfer = tx is not None and is_transfer(tx)
    await _assert_household_isolation(session, debts, tx)
    linked_amount = await _validate_linked_transaction(
        session,
        tx,
        settlement_type=settlement_type,
        by_user_id=by_user_id,
        is_actual_transfer=is_actual_transfer,
    )
    debt_contexts = await _build_debt_contexts(session, debts)

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
    await _persist_settlement_lines(session, settlement, lines, debt_contexts)
    return settlement


async def list_settlements_between(
    session: AsyncSession, *, caller_id: UUID, with_user_id: UUID
) -> list[Settlement]:
    """Règlements touchant une dette entre `{caller, with}` (TOUT restant — D9).

    Bornage du périmètre = token (`caller_id`) ; `with_user_id` = filtre de
    contrepartie APRÈS bornage (anti-IDOR, gabarit `list_debts_for_user`). Inclut
    les règlements de dettes SOLDÉES (`remaining == 0`) — `list_open_debts_between`
    les exclurait (filtre `remaining > 0`, S10.3 D7) alors que c'est justement là
    qu'un règlement a eu lieu (D9). Requête dédiée, distincte de
    `list_open_debts_between` (réservé au calcul du restant ouvert). Tri
    déterministe `(settled_at DESC, id)` — contrat observable (tiebreaker `id`).
    """
    pair = or_(
        and_(Debt.from_user_id == caller_id, Debt.to_user_id == with_user_id),
        and_(Debt.from_user_id == with_user_id, Debt.to_user_id == caller_id),
    )
    stmt = (
        select(Settlement)
        # `.distinct()` : la double jointure `SettlementLine`→`Debt` produit une
        # ligne PAR `SettlementLine` matchant `pair` ; un règlement multi-lignes
        # sur le même couple apparaîtrait donc N fois. `DISTINCT` dédoublonne au
        # niveau `Settlement` (l'ORDER BY ne porte que sur des colonnes de
        # `Settlement`, donc compatible avec `SELECT DISTINCT`).
        .distinct()
        .join(SettlementLine, SettlementLine.settlement_id == Settlement.id)
        .join(Debt, Debt.id == SettlementLine.debt_id)
        .where(pair)
        .order_by(Settlement.settled_at.desc(), Settlement.id)
    )
    return list((await session.execute(stmt)).scalars().all())


async def get_settlement_detail(
    session: AsyncSession, *, settlement_id: UUID, by_user_id: UUID
) -> tuple[Settlement, list[SettlementLine], list[DebtWithContext]]:
    """Détail d'un règlement : méta + lignes (restreintes) + dettes masquées.

    RBAC (D11) : le caller doit être partie d'AU MOINS UNE dette du règlement →
    sinon **404 uniforme** (anti-oracle, jamais 403). **S-M1 (défense en
    profondeur)** : ne projeter QUE les dettes dont le caller est partie — la
    garantie « 2 contreparties » du validateur de CRÉATION n'est PAS maintenue en
    SQL, et `_project_debt` ne masque que `source_transaction_id`/`account_id` du
    DÉBITEUR ; pour une dette dont le caller n'est ni `from` ni `to`,
    `from/to/amount/remaining/label/cat/date` fuiteraient. Le filtre par-dette est
    la barrière de lecture. Les `lines` renvoyées sont elles aussi restreintes aux
    dettes visibles (pas de fuite du `debt_id` d'un tiers).

    Le masquage est délégué au helper centralisé S09.4 (`project_debts_by_ids` →
    `_project_debt`) : aucun chemin de lecture parallèle ; `materialization_trace`
    jamais exposé (absent du DTO par construction).
    """
    settlement = await session.get(Settlement, settlement_id)
    if settlement is None:
        raise SettlementDebtNotAccessibleError  # 404 uniforme (anti-oracle)
    all_lines = list(
        (
            await session.execute(
                select(SettlementLine).where(SettlementLine.settlement_id == settlement_id)
            )
        )
        .scalars()
        .all()
    )
    debt_ids = [ln.debt_id for ln in all_lines]
    debts: list[Debt] = []
    if debt_ids:
        debts = list(
            (await session.execute(select(Debt).where(Debt.id.in_(debt_ids)))).scalars().all()
        )
    # RBAC : partie d'AU MOINS UNE dette → sinon 404 (S-M1 : filtre par-dette).
    visible_debt_ids: set[UUID] = {
        d.id for d in debts if by_user_id in (d.from_user_id, d.to_user_id)
    }
    if not visible_debt_ids:
        raise SettlementDebtNotAccessibleError  # 404 uniforme (anti-oracle)
    # Ne projeter / renvoyer QUE les dettes (et lignes) dont le caller est partie.
    projected = await project_debts_by_ids(
        session, debt_ids=list(visible_debt_ids), reader_id=by_user_id
    )
    visible_lines = [ln for ln in all_lines if ln.debt_id in visible_debt_ids]
    return settlement, visible_lines, projected
