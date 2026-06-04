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
from typing import Any

from sqlalchemy import (
    ARRAY,
    UUID,
    BigInteger,
    CheckConstraint,
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
    # `default`/`force_full_debt`/`force_no_debt` (domain Literal). The value
    # lock lives at the domain boundary (S07.3), backed by a defense-in-depth
    # `CheckConstraint` below (added S07.4/D14): unlike `currency`/`state`
    # (open sets kept ENUM/CHECK-free for V2 evolution), this is a *closed*
    # 3-value set driving a sensitive budget mechanic, and `update_editable_fields`
    # can write it post-confirmed via a `model_copy` path that bypasses Pydantic
    # — so the DB CHECK is the fail-closed backstop.
    debt_generation_override: Mapped[str] = mapped_column(
        String,
        nullable=False,
        default="default",
    )
    # Edit handle of the `ShareRequest → Transaction` canonical link (S07.4):
    # nullable UUID, mutable after `confirmed` (ADR 0001 allowed set, domain
    # `EDITABLE_AFTER_CONFIRMED`). Laid nullable WITHOUT a FK in S07.4/0010
    # (the `share_requests` table did not exist yet); E09/S09.1 activates the
    # FK `→ share_requests.id` `ON DELETE SET NULL` (revoking a SR keeps the tx
    # pointed at the now-`revoked` row — voulu). The FK is declared BY STRING
    # (no Python import of `ShareRequest`, no relationship) so the import-linter
    # graph stays directional (`debts → transactions`, never the reverse). It is
    # `use_alter=True`: `transactions.share_request_id → share_requests` and
    # `share_requests.source_transaction_id → transactions` form a (nullable)
    # cycle, so `create_all` emits this one as a post-CREATE `ALTER TABLE`
    # (mirroring 0014's separate `op.create_foreign_key`) to break it. No index
    # yet (no read path filters it; matches the migration / snapshot).
    share_request_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "share_requests.id",
            ondelete="SET NULL",
            name="fk_transactions_share_request_id_share_requests",
            use_alter=True,
        ),
        nullable=True,
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
        # Closed 3-value set (domain `DebtGenerationOverride` Literal) →
        # defense-in-depth CHECK (D14). Unlike `state`/`currency` (open sets
        # kept ENUM/CHECK-free for V2), this drives a sensitive debt mechanic
        # (ADR 0011) and is editable post-confirmed via `update_editable_fields`
        # (whose `model_copy` path bypasses Pydantic) — so the DB is the
        # fail-closed backstop. Mirrors the domain Literal exactly.
        # `name="debt_generation_override"` (not the full `ck_transactions_…`):
        # the `NAMING_CONVENTION` `ck_%(table_name)s_%(constraint_name)s` prefixes
        # it to `ck_transactions_debt_generation_override`, matching the
        # `op.f("ck_transactions_debt_generation_override")` in migration 0010
        # (gabarit `ck_household_singleton`).
        CheckConstraint(
            "debt_generation_override IN ('default', 'force_full_debt', 'force_no_debt')",
            name="debt_generation_override",
        ),
    )


def _default_leg_role(context: Any) -> str:
    """Default context-sensitive : dérive `leg_role` de `category_id` à
    l'INSERT (même règle que le back-fill 0013 et le validator domaine).

    Rend `leg_role` NOT NULL « gratuit » pour `add_split` et les factories sans
    qu'aucun ne le passe explicitement. L'assignation serveur DURCIE (dérivée de
    la forme canonique, jamais du payload client) arrive en S08.5.2/S08.5.3 ;
    ici aucune entrée client n'existe pour `leg_role` (le schema S07.5 ne
    l'expose pas), donc « jamais depuis le client » est trivialement vrai.
    """
    params = context.get_current_parameters()
    return "funding" if params.get("category_id") is None else "classification"


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

    `leg_role` (ADR 0017, option 1, S08.5.1) : marqueur STRUCTUREL du rôle de
    la jambe — `funding` (mouvement de compte, exempté de catégorie) vs
    `classification` (jambe de dépense). Set fermé 2-valeurs → `String` NOT NULL
    + `CheckConstraint` defense-in-depth (gabarit `debt_generation_override`),
    PAS un ENUM (aligné sur `state`/`currency`, le `Literal` source de vérité
    `LegRole` vit au domaine). Colonne **server-authoritative**, valeur dérivée
    de `category_id` par `_default_leg_role` à l'INSERT (même règle que le
    back-fill 0013). Pas d'index (set à 2 valeurs, aucune requête ne le filtre).
    Pas de règles de sync PowerSync à éditer (aucun artefact ; client = E14,
    ADR 0003) : sync-safe, à inclure quand les sync rules seront écrites.
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
    # creates `savings`. No active FK to protect ⇒ no index here yet; the
    # "fast-aggregate" index CONTEXT.md §`split.savings_goal_id` calls for is
    # deferred to that same story (added alongside the constraint, after any
    # orphan UUIDs are cleaned, once the column actually carries values).
    savings_goal_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
    )
    # `funding`/`classification` (domaine `LegRole`). `Mapped[str]` (et non
    # `Mapped[Literal]`) aligne sur `state`/`debt_generation_override` ; le
    # verrou de valeurs vit au domaine (gabarit), doublé du `CheckConstraint`
    # ci-dessous (backstop fail-closed). `default=_default_leg_role` (Python,
    # PAS server_default) dérive la valeur de `category_id` à l'INSERT et
    # préserve la parité create_all/Alembic du snapshot.
    leg_role: Mapped[str] = mapped_column(
        String,
        nullable=False,
        default=_default_leg_role,
    )

    __table_args__ = (
        Index("ix_splits_transaction_id", "transaction_id"),
        Index("ix_splits_account_id", "account_id"),
        Index("ix_splits_category_id", "category_id"),
        # Set fermé 2-valeurs (domaine `LegRole`) → CHECK defense-in-depth
        # (gabarit `debt_generation_override`). `name="leg_role"` → préfixé
        # `ck_splits_leg_role` par NAMING_CONVENTION, à matcher byte-for-byte
        # dans la migration 0013 via `op.f("ck_splits_leg_role")`.
        CheckConstraint(
            "leg_role IN ('funding', 'classification')",
            name="leg_role",
        ),
    )
