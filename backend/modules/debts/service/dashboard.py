"""Lecture du dashboard dettes (S09.4) — bornée au token, allowlist + masquage.

Chemin de lecture UNIQUE des dettes côté serveur : `list_debts_for_user` (et
`aggregate_by_counterparty`, P09.4.3) passent toutes deux par `_project_debt`,
le seul constructeur de `DebtWithContext`. Pas de chemin parallèle qui
ré-exposerait un champ source (review #22).

Masquage (review #22 B1) : `source_transaction_id` ET `account_id` → None pour le
non-owner du compte source. Pour une `personal_share_request`, owner = créancier
(`requested_by = to_user_id`) ⇒ masquer ssi le lecteur est le débiteur
(`reader == from_user_id`). Renforce ADR 0003 (qui ne masquait que
`source_transaction_id`) ; la sync rule E13 devra masquer les DEUX colonnes
(note de renvoi ajoutée à l'ADR 0003 pour fermer le risque temporel côté sync).

Enrichissement à la lecture : `short_label` (join `share_requests` actif),
`category_id`/`date` (join Core sur la tx source — valeur FRAÎCHE, `category_id`
restant éditable après `confirmed`, glossaire §50 ; jamais dénormalisé sur Debt).
La table PEER `transactions` est lue en SQLAlchemy Core (handle `table()`), JAMAIS
importée (contrat `2-debts` ; mirror `budget/service/consumption.py`).

Lecture seule (ADR 0002/0015) : aucun `flush()`/`commit()`, aucune mutation.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from enum import StrEnum
from typing import Any  # pour Row[Any] (pyright strict : Row non paramétré → warning)
from uuid import UUID

from sqlalchemy import Row, and_, column, or_, select, table
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.debts.models import Debt, ShareRequest
from backend.shared.money import Money

__all__ = [
    "CounterpartyNet",
    "DebtDirection",
    "DebtWithContext",
    "aggregate_by_counterparty",
    "list_debts_for_user",
]

# Handle Core léger sur la table PEER `transactions` (contrat 1 : debts > transactions,
# mais on lit par NOM sans importer transactions.models — mirror budget/consumption).
_transactions = table("transactions", column("id"), column("category_id"), column("date"))


class DebtDirection(StrEnum):
    """Sens de lecture, TOUJOURS relatif au token (jamais un sélecteur de tiers)."""

    ALL = "all"
    OWED_TO_ME = "owed_to_me"  # je suis créancier : to_user_id == token
    OWED_BY_ME = "owed_by_me"  # je suis débiteur : from_user_id == token


@dataclass(frozen=True, slots=True)
class DebtWithContext:
    """Vue allowlist d'une dette (déjà masquée). Set de champs EXPLICITE.

    `materialization_trace` est ABSENT par construction (pas de champ) ⇒
    impossible à fuiter. `source_transaction_id`/`account_id` sont nullables :
    `None` quand masqués au débiteur (D5).
    """

    from_user_id: UUID
    to_user_id: UUID
    amount_cents: int
    currency: str
    origin: str
    requested_by: UUID
    short_label: str | None
    category_id: UUID | None
    date: dt.date | None
    created_at: dt.datetime
    source_transaction_id: UUID | None  # masqué (None) si reader != owner
    account_id: UUID | None  # masqué (None) si reader != owner


def _reader_owns_source(*, origin: str, reader_id: UUID, to_user_id: UUID) -> bool:
    """Le lecteur est-il owner du compte source ? (fail-safe : défaut False).

    E09 : seule l'origine `personal_share_request` existe ; owner = créancier
    (`requested_by = to_user_id`). `shared_account_overflow` (E11) tombera dans le
    défaut `False` (masqué) tant que sa logique d'ownership n'est pas ajoutée.
    """
    return origin == "personal_share_request" and reader_id == to_user_id


def _project_debt(
    debt: Debt,
    *,
    reader_id: UUID,
    short_label: str | None,
    category_id: UUID | None,
    date: dt.date | None,
) -> DebtWithContext:
    """UNIQUE constructeur de `DebtWithContext` : allowlist + masquage (D6)."""
    owns = _reader_owns_source(origin=debt.origin, reader_id=reader_id, to_user_id=debt.to_user_id)
    return DebtWithContext(
        from_user_id=debt.from_user_id,
        to_user_id=debt.to_user_id,
        amount_cents=debt.amount_cents,
        currency=debt.currency,
        origin=debt.origin,
        # = requested_by pour personal_share_request (créancier = owner).
        # ⚠️ À REVISITER en E11 : `shared_account_overflow` n'a pas de SR, donc
        # `to_user_id` n'y porte pas la sémantique « requested_by » — adapter alors.
        requested_by=debt.to_user_id,
        short_label=short_label,
        category_id=category_id,
        date=date,
        created_at=debt.created_at,
        source_transaction_id=debt.source_transaction_id if owns else None,
        account_id=debt.account_id if owns else None,
    )


async def list_debts_for_user(
    session: AsyncSession,
    *,
    user_id: UUID,
    direction: DebtDirection = DebtDirection.ALL,
    counterparty: UUID | None = None,
) -> list[DebtWithContext]:
    """Dettes où `user_id` (= token) est créancier OU débiteur, jamais d'un tiers.

    Bornage TOUJOURS appliqué (`from_user_id == user_id OR to_user_id == user_id`).
    `direction` restreint au sens ; `counterparty` (= `with`) filtre la contrepartie
    APRÈS bornage — jamais un sélecteur de propriétaire (anti-IDOR, D9).

    Enrichissement : LEFT JOIN `share_requests` actif (short_label, sur la paire
    (tx, débiteur)) + LEFT JOIN Core `transactions` (category_id, date frais).
    """
    bornage = or_(Debt.from_user_id == user_id, Debt.to_user_id == user_id)
    if direction is DebtDirection.OWED_TO_ME:
        bornage = Debt.to_user_id == user_id
    elif direction is DebtDirection.OWED_BY_ME:
        bornage = Debt.from_user_id == user_id

    conds = [bornage]
    if counterparty is not None:
        # contrepartie APRÈS bornage : la dette relie le token et `counterparty`
        conds.append(
            or_(
                and_(Debt.from_user_id == user_id, Debt.to_user_id == counterparty),
                and_(Debt.to_user_id == user_id, Debt.from_user_id == counterparty),
            )
        )

    stmt = (
        select(
            Debt,
            ShareRequest.short_label,
            _transactions.c.category_id,
            _transactions.c.date,
        )
        .outerjoin(
            ShareRequest,
            and_(
                ShareRequest.source_transaction_id == Debt.source_transaction_id,
                ShareRequest.requested_from == Debt.from_user_id,
                ShareRequest.revoked_at.is_(None),
            ),
        )
        .outerjoin(_transactions, _transactions.c.id == Debt.source_transaction_id)
        .where(*conds)
        .order_by(Debt.created_at, Debt.id)  # ordre déterministe (tests + UX)
    )
    rows: list[Row[Any]] = list((await session.execute(stmt)).all())
    return [
        _project_debt(r[0], reader_id=user_id, short_label=r[1], category_id=r[2], date=r[3])
        for r in rows
    ]


# --- Agrégat par contrepartie (P09.4.3) ------------------------------------


@dataclass(frozen=True, slots=True)
class CounterpartyNet:
    """Net orienté par contrepartie (D10). `net_amount_cents` signé.

    Positif = la contrepartie me doit net ; négatif = je lui dois net. Aucun
    champ source ne transite (l'agrégat est dérivé de `DebtWithContext` déjà
    masqués).
    """

    user_id: UUID
    net_amount_cents: int
    currency: str
    debts_count: int


def _aggregate_net(debts: list[DebtWithContext], *, viewer_id: UUID) -> list[CounterpartyNet]:
    """PUR : agrège par contrepartie le net orienté (testable example-based).

    net(C) = Σ(dettes C→moi) − Σ(dettes moi→C). `+` quand C me doit, `−` quand
    je dois à C. Centimes via `Money` (lève `IncompatibleCurrencyError` sur
    devises mixtes — fail-safe ADR 0008). Tri déterministe par `user_id`.
    """
    nets: dict[UUID, Money] = {}
    counts: dict[UUID, int] = {}
    for d in debts:
        if d.to_user_id == viewer_id:  # C = from_user_id me doit
            cp, signed = d.from_user_id, Money(d.amount_cents, d.currency)  # type: ignore[arg-type]
        else:  # je dois à C = to_user_id
            cp, signed = d.to_user_id, Money(-d.amount_cents, d.currency)  # type: ignore[arg-type]
        nets[cp] = nets[cp] + signed if cp in nets else signed
        counts[cp] = counts.get(cp, 0) + 1
    return [
        CounterpartyNet(
            user_id=cp,
            net_amount_cents=m.amount_cents,
            currency=m.currency,
            debts_count=counts[cp],
        )
        for cp, m in sorted(nets.items(), key=lambda kv: str(kv[0]))  # ordre déterministe
    ]


async def aggregate_by_counterparty(
    session: AsyncSession, *, user_id: UUID
) -> list[CounterpartyNet]:
    """Agrégat par contrepartie via le MÊME chemin de lecture (D6) — aucun champ
    source ne transite (les `DebtWithContext` consommés sont déjà masqués)."""
    debts = await list_debts_for_user(session, user_id=user_id)
    return _aggregate_net(debts, viewer_id=user_id)
