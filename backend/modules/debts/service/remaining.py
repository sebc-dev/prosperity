"""Solde restant d'une `Debt` — primitives serveur pure-lecture (S10.3).

Le solde restant n'est **jamais matérialisé** (ADR 0011 ; `Debt` reste une
projection read-only, ADR 0002) : il se calcule par différence
`debt.amount_cents − Σ settlement_lines.amount_cents` à chaque lecture. Aucune
colonne ni migration.

Deux primitives, exposées via `debts.public` pour réutilisation par le service
`create_settlement` (S10.4 : refus d'over-settlement) et l'epic E11 (overflow
F10) :

- `compute_remaining(debt_id)` — solde d'une dette (`DebtNotFoundError` si la
  dette n'existe pas, ≠ remaining 0).
- `list_open_debts_between(user_a, user_b)` — dettes encore ouvertes
  (`remaining > 0`) entre deux contreparties, orientées, avec leur restant.

⚠️ **Primitives NON bornées au token ni au foyer** (D9) : elles renvoient le
restant de N'IMPORTE QUELLE dette / N'IMPORTE QUEL couple d'utilisateurs. Le
bornage AuthZ et l'isolation foyer sont à la charge de l'appelant
(`create_settlement` S10.4 / E11) — voir les docstrings. NE JAMAIS router
directement.

`_settled_subq` est l'expression PARTAGÉE de la somme apurée (importée par
`dashboard.py`, intra-`debts.service`) : une seule source de vérité de la
formule (zéro divergence entre les sites d'appel).

Lecture seule (ADR 0002) : aucun `flush()`/`commit()`, aucune mutation. Importe
uniquement `debts.models` (intra-module) + sqlalchemy → aucun arc import-linter
nouveau (contrat `2-debts`).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import ClassVar
from uuid import UUID

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import InstrumentedAttribute
from sqlalchemy.sql.elements import ColumnElement

from backend.modules.debts.models import Debt, SettlementLine

__all__ = [
    "DebtNotFoundError",
    "OpenDebt",
    "compute_remaining",
    "compute_remaining_for_debts",
    "list_open_debts_between",
]


class DebtNotFoundError(Exception):
    """`debt_id` inexistant (≠ remaining 0). `code` stable, SANS PII.

    Le message d'instance est STATIQUE (aucun UUID) — `str(exc)` ne contient
    jamais le `debt_id`, verrouillé par `test_error_codes_are_stable_and_pii_free`.
    ⚠️ S10.4 : la distinction `not-found`/`remaining 0` devient un oracle
    d'énumération d'UUID dès qu'une route l'expose → mapper APRÈS la garde AuthZ.
    """

    code: ClassVar[str] = "debt_not_found"


@dataclass(frozen=True, slots=True)
class OpenDebt:
    """Dette ouverte (`remaining > 0`) entre deux contreparties (DTO interne).

    `@dataclass` (pas Pydantic) : DTO in-process, pas un boundary à valider
    (gabarit `DebtWithContext`/`CounterpartyNet`). Exposé via `debts.public`
    pour E11. Ne porte AUCUN champ source (`source_transaction_id`/`account_id`
    absents) → pas de fuite à l'export (D4).
    """

    debt_id: UUID
    from_user_id: UUID  # débiteur
    to_user_id: UUID  # créancier
    amount_cents: int
    remaining_cents: int  # > 0 par construction (WHERE remaining > 0) ; jamais clampé (D2)
    currency: str


def _settled_subq(
    debt_id_col: ColumnElement[UUID] | InstrumentedAttribute[UUID],
) -> ColumnElement[int]:
    """Σ des lignes d'apurement d'UNE dette, corrélée à la colonne PK fournie.

    Expression PARTAGÉE (D1) : réutilisée par `compute_remaining`,
    `list_open_debts_between` ET `dashboard.py` (intra-`debts.service`) ⇒ une
    seule source de vérité de la formule. `coalesce(.., 0)` : une dette sans
    ligne somme à 0, jamais NULL. Aucun filtre `settlement_id` → agrège
    **cross-settlement** (toutes les lignes de la dette, tous parents confondus).
    Privé (NON ré-exporté par `public.py`).
    """
    return func.coalesce(
        select(func.sum(SettlementLine.amount_cents))
        .where(SettlementLine.debt_id == debt_id_col)
        .scalar_subquery(),
        0,
    )


async def compute_remaining(session: AsyncSession, *, debt_id: UUID) -> int:
    """debt.amount_cents − COALESCE(SUM(settlement_lines.amount_cents), 0).

    Lève `DebtNotFoundError` si la dette n'existe pas (≠ remaining 0). NE clampe
    PAS un restant négatif (D2/ADR 0011) : un over-settlement passé au travers
    du validateur doit rester visible, pas masqué à la lecture.

    ⚠️ Primitive serveur NON bornée au token ni au foyer (D9) : renvoie le
    restant de N'IMPORTE QUELLE dette. Le bornage AuthZ et l'isolation foyer
    sont à la charge de l'appelant (service `create_settlement` S10.4 / E11).
    NE JAMAIS exposer directement via une route sans garde d'appartenance.
    """
    stmt = select(Debt.amount_cents - _settled_subq(Debt.id)).where(Debt.id == debt_id)
    remaining = (await session.execute(stmt)).scalar_one_or_none()
    # Invariant (D1) : `Debt.amount_cents` est NOT NULL et `_settled_subq` est
    # `coalesce(.., 0)` ⇒ l'expression sélectionnée n'est JAMAIS NULL pour une
    # ligne existante. Donc `remaining is None` ⟺ aucune ligne `debts` ⟺ dette
    # inexistante (et non « restant nul »).
    if remaining is None:
        raise DebtNotFoundError("debt does not exist")
    # Postgres `SUM(bigint)` est `numeric` ⇒ l'expression remonte un `Decimal` ;
    # on rétablit le contrat `int` (centimes) attendu par les appelants.
    return int(remaining)


async def compute_remaining_for_debts(
    session: AsyncSession, *, debt_ids: Sequence[UUID]
) -> dict[UUID, int]:
    """`{debt_id: remaining}` pour un LOT de dettes, en UNE seule requête.

    Variante batchée de `compute_remaining` (évite le N+1 quand un règlement
    multi-lignes apure plusieurs dettes — gabarit `dashboard.py` qui agrège déjà
    `_settled_subq` en une passe). MÊME formule et MÊMES invariants : `_settled_subq`
    partagé, restant JAMAIS clampé (D2/ADR 0011 : un over-settlement reste visible).

    Contrairement à `compute_remaining`, NE lève PAS `DebtNotFoundError` : un
    `debt_id` inexistant est simplement ABSENT du dict (l'appelant `create_settlement`
    a déjà prouvé l'existence des dettes en (i) avant d'appeler). ⚠️ Primitive NON
    bornée au token ni au foyer (D9) — bornage AuthZ/foyer à la charge de l'appelant.
    """
    if not debt_ids:
        return {}
    stmt = select(Debt.id, Debt.amount_cents - _settled_subq(Debt.id)).where(Debt.id.in_(debt_ids))
    rows = (await session.execute(stmt)).all()
    # `SUM(bigint)` est `numeric` en Postgres ⇒ cast vers le contrat int (centimes).
    return {r[0]: int(r[1]) for r in rows}


async def list_open_debts_between(
    session: AsyncSession, *, user_a: UUID, user_b: UUID
) -> list[OpenDebt]:
    """Dettes (les DEUX sens) entre {user_a, user_b} dont remaining > 0.

    Symétrique : (from=a,to=b) OU (from=b,to=a). Orientation (`from`/`to`)
    préservée. Tri déterministe `(created_at, id)`. Filtre `remaining > 0` en
    `WHERE` (D1).

    ⚠️ Primitive serveur NON bornée au foyer (D9) : accepte un couple ARBITRAIRE
    d'utilisateurs. L'appelant (S10.4/E11) DOIT vérifier que les deux users
    appartiennent au même foyer que le token avant usage. NE JAMAIS router
    directement.
    """
    # Expression `remaining` STOCKÉE UNE FOIS : réutilisée par le `.label()` du
    # SELECT ET le filtre `.where()` — pas de ré-écriture divergente.
    remaining_expr = Debt.amount_cents - _settled_subq(Debt.id)
    remaining = remaining_expr.label("remaining")
    stmt = (
        select(
            Debt.id, Debt.from_user_id, Debt.to_user_id, Debt.amount_cents, Debt.currency, remaining
        )
        .where(
            or_(
                and_(Debt.from_user_id == user_a, Debt.to_user_id == user_b),
                and_(Debt.from_user_id == user_b, Debt.to_user_id == user_a),
            ),
            # `remaining > 0` est un filtre ligne-à-ligne : la requête externe ne
            # contient AUCUN agrégat (la somme vit dans la sous-requête scalaire
            # corrélée `_settled_subq`), et sans JOIN aucune duplication de ligne
            # n'est possible ⇒ `WHERE` est l'idiome correct (ni `GROUP BY` ni
            # `HAVING` nécessaires).
            remaining_expr > 0,
        )
        .order_by(Debt.created_at, Debt.id)
    )
    rows = (await session.execute(stmt)).all()
    return [
        OpenDebt(
            debt_id=r.id,
            from_user_id=r.from_user_id,
            to_user_id=r.to_user_id,
            amount_cents=r.amount_cents,
            # `SUM(bigint)` est `numeric` en Postgres ⇒ cast vers le contrat int.
            remaining_cents=int(r.remaining),
            currency=r.currency,
        )
        for r in rows
    ]
