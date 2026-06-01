"""ORM models for the transactions module (F05 socle persisté).

Premiers modèles du module (qui n'avait que `__init__.py` + `public.py`).
Archétype structurel des modules à `domain.py` : `models.py` est du SQLA
**pur**, sans logique métier — l'invariant zero-sum, la state machine et
l'immutabilité (ADR 0001) vivent dans `domain.py` (S07.3).

Pas de colonne `amount` (dérivée des splits) ni `bank_transaction_id`
(porté par `Reconciliation`, ADR 0006 / E13). `state` et
`debt_generation_override` sont des colonnes `String` SANS CHECK SQL : le
verrou de valeurs vit au boundary domain (gabarit `Account.currency`).

Layering (ADR 0005, contrat 1) : `transactions ⟂ budget` (même couche).
Les FK vers `categories` sont déclarées **par chaîne**
(`ForeignKey("categories.id")`), résolues au runtime par SQLAlchemy SANS
import Python de `Category` — aucune nouvelle exception import-linter.

Surface publique : ce module n'est importable que depuis `transactions`
(contrat 2 ; `transactions.models` listé en `forbidden_modules`).
"""

from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import (
    ARRAY,
    UUID,
    BigInteger,
    Date,
    DateTime,
    ForeignKey,
    Index,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from backend.shared.models import Base


class Transaction(Base):
    """Mouvement financier daté, attaché à un compte, composé de splits
    zero-sum (CONTEXT.md §Transaction).

    `account_id` est dénormalisé ici (clé de bucket PowerSync E13 + filtre
    principal de la route liste S07.5) en plus de vivre sur chaque `Split`.
    `ON DELETE RESTRICT` : un compte n'est jamais hard-deleted (archive, F02).

    `state` : `draft`/`planned`/`confirmed`/`void` côté domain (Literal,
    S07.3) — colonne `String` sans CHECK ni ENUM, le verrou vit au domain
    (gabarit `Account.currency`, pas `Account.type` ENUM).

    `category_id` : catégorie « principale », NULL si transfert. FK par
    chaîne (`transactions ⟂ budget`), `ON DELETE RESTRICT` (jumeau DB de la
    règle « pas de cascade », CONTEXT.md §Catégorie).

    `created_by` : `ON DELETE RESTRICT` (F02 — un user est désactivé,
    jamais supprimé). `confirmed_at`/`voided_at` NULL tant que la
    transition n'a pas eu lieu (S07.4).

    PAS de colonne `amount` (dérivée `sum(splits.amount_cents)`, invariant
    zero-sum au domain S07.3) ni `bank_transaction_id` (porté par
    `Reconciliation`, ADR 0006 / E13).
    """

    __tablename__ = "transactions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "accounts.id",
            ondelete="RESTRICT",
            name="fk_transactions_account_id_accounts",
        ),
        nullable=False,
    )
    date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    state: Mapped[str] = mapped_column(String, nullable=False)
    payee: Mapped[str | None] = mapped_column(String(255), nullable=True)
    description: Mapped[str | None] = mapped_column(String, nullable=True)
    category_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "categories.id",
            ondelete="RESTRICT",
            name="fk_transactions_category_id_categories",
        ),
        nullable=True,
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "users.id",
            ondelete="RESTRICT",
            name="fk_transactions_created_by_users",
        ),
        nullable=False,
    )
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    confirmed_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    voided_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    tags: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False, default=list)
    debt_generation_override: Mapped[str] = mapped_column(
        String,
        nullable=False,
        default="default",
    )

    __table_args__ = (
        # Each FK is indexed (gabarit `ix_accounts_owner_id`): without an
        # index Postgres seq-scans `transactions` on every RESTRICT delete of
        # the parent. `account_id` also serves the PowerSync bucket (E13) and
        # the list-route filter (S07.5). `default`/`tags`/`state` carry ORM
        # Python-side defaults (not `server_default`) so `create_all` and the
        # migration stay byte-for-byte at parity in the snapshot.
        Index("ix_transactions_account_id", "account_id"),
        Index("ix_transactions_category_id", "category_id"),
        Index("ix_transactions_created_by", "created_by"),
    )


class Split(Base):
    """Une ligne signée d'une transaction (CONTEXT.md §Split). Une
    transaction est une collection de splits zero-sum.

    `transaction_id` : `ON DELETE CASCADE` — un split n'a aucun sens hors
    de sa transaction (gabarit `account_members.account_id`). `account_id`
    (RESTRICT) peut viser un AUTRE compte du foyer que la transaction (cas
    transfert). `category_id` (RESTRICT, NULL) : transfert ou split draft.

    `amount_cents` (BigInteger) + `currency` (String(3)) : colonnes brutes
    mappées vers/depuis `Money` par le service (S07.4) — `Money` n'est PAS
    un modèle ORM (cf. `shared/money.py`).

    `savings_goal_id` : colonne UUID nullable de **préparation** (E12/savings,
    CONTEXT.md §`split.savings_goal_id`). SANS `ForeignKey` active : la table
    `savings_goals` n'existe pas encore — option (a) de l'issue, pour ne pas
    rejouer cette migration plus tard. La story qui crée `savings` ajoutera
    la contrainte + l'index dans sa propre migration (après nettoyage des
    UUID orphelins éventuels).
    """

    __tablename__ = "splits"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    transaction_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "transactions.id",
            ondelete="CASCADE",
            name="fk_splits_transaction_id_transactions",
        ),
        nullable=False,
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "accounts.id",
            ondelete="RESTRICT",
            name="fk_splits_account_id_accounts",
        ),
        nullable=False,
    )
    category_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "categories.id",
            ondelete="RESTRICT",
            name="fk_splits_category_id_categories",
        ),
        nullable=True,
    )
    amount_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    # Dormant FK: nullable UUID column WITHOUT a `ForeignKey` (savings_goals
    # does not exist yet — option (a)). To be activated by the story that
    # creates `savings`. No FK ⇒ no dedicated index (nothing to protect).
    savings_goal_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
    )

    __table_args__ = (
        Index("ix_splits_transaction_id", "transaction_id"),
        Index("ix_splits_account_id", "account_id"),
        Index("ix_splits_category_id", "category_id"),
    )
