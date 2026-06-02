"""ORM models for the budget module.

Categories live here (CONTEXT.md §Catégorie): they are consumed almost
exclusively by budgets and transactions, so the budget module owns them
code-side. S06.1 ships only the `Category` socle; `domain.py`
(CycleDetector) and the category service arrive in S06.2.

`Category` is a self-referencing tree (`parent_id` → `categories.id`).
No SQL cycle constraint: acyclicity is enforced at the service layer
(S06.2 `CycleDetector`, walk-up of ancestors). The self-FK is
`ON DELETE RESTRICT` — deleting a category that still has children is
refused at the DB (defense-in-depth doubling the S06.3 service rule;
CONTEXT.md "pas de cascade, pas de re-parentage automatique").

Cross-module callers reach categories via `budget.public` — import-linter
contract `2-budget` (and contract 2's globs for the other sources) forbids
importing this module from outside `budget`.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import (
    UUID,
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    SmallInteger,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from backend.shared.models import Base


class Category(Base):
    """A node of the unbounded category tree (CONTEXT.md §Catégorie).

    `parent_id` NULL = a root. `ON DELETE RESTRICT` (not CASCADE, not
    SET NULL): a category with sub-categories cannot be hard-deleted —
    the service archives instead (S06.3). RESTRICT is the DB-level twin
    of that rule; SET NULL would silently orphan a subtree, CASCADE
    would mass-delete children — both forbidden by CONTEXT.md.

    `color` is `String(7)` (hex `#RRGGBB`) **without** a CHECK: the format
    is validated at the Pydantic boundary in S06.3 (gabarit `currency`),
    keeping the palette evolvable without a migration. `icon` is an
    unbounded label, also UI-defaulted. Both nullable — no magic
    "Sans catégorie" default (cf. CONTEXT.md `splits.category_id NULL`).

    `archived_at` backs the soft-delete of S06.3 (DELETE = archive);
    posted now to avoid a one-column migration later (gabarit
    `Account.archived_at`).
    """

    __tablename__ = "categories"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    color: Mapped[str | None] = mapped_column(String(7), nullable=True)
    icon: Mapped[str | None] = mapped_column(String, nullable=True)
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "categories.id",
            ondelete="RESTRICT",
            name="fk_categories_parent_id_categories",
        ),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    archived_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    __table_args__ = (
        # Plain index on the self-FK: required so the `ON DELETE RESTRICT`
        # referential check (and the S06.2 walk-up of ancestors) does not
        # seq-scan `categories` — both must see ALL rows, archived
        # included, so a partial index cannot serve them (gabarit
        # `ix_accounts_owner_id`).
        Index("ix_categories_parent_id", "parent_id"),
        # Partial index for the active-listing path (S06.3
        # `GET /categories?include_archived=false`): indexes only live
        # rows, so active roots (`parent_id IS NULL AND archived_at IS NULL`)
        # and active children are fetched without touching archived
        # tombstones. The `postgresql_where` must match the migration's
        # byte-for-byte (create_all/Alembic parity — same trap as
        # `uq_invitations_pending_email`).
        Index(
            "ix_categories_active",
            "parent_id",
            postgresql_where=text("archived_at IS NULL"),
        ),
    )


class Budget(Base):
    """Montant alloué à une catégorie sur une période, avec scope perso/commun
    et liste de contributeurs (CONTEXT.md §Budget). Agrège à la **lecture** les
    splits des sous-catégories (S08.2) — aucune logique métier ici (socle ORM).

    `category_id` → `categories.id` `ON DELETE RESTRICT` : supprimer une
    catégorie encore référencée par un budget est refusé au niveau DB (jumeau
    de « pas de cascade », CONTEXT.md §Catégorie). FK déclarée par chaîne (même
    si `categories` est intra-module) par cohérence — aucun import de classe.

    `period_kind` (`monthly`/`quarterly`/`yearly`) et `scope`
    (`personal`/`shared`) sont des `String` **sans CHECK** : sets fermés
    verrouillés au boundary Pydantic (S08.4), gardés évolutifs sans migration
    (gabarit `Category.color`, `Transaction.state`). Diffère du CHECK de
    `debt_generation_override` (set figé + chemin d'écriture hors Pydantic).

    `period_start` est l'**ancre** d'une fenêtre récurrente (S08.2
    `compute_period_window`), pas une borne unique : un mensuel ancré le 15
    ouvre `[15, 15 du mois suivant)`. V1 attend le 1er du mois.

    `amount_cents` (`BigInteger`) + `currency` (`String(3)`) : colonnes brutes
    mappées vers/depuis `Money` par le service (S08.4). Budget mono-devise
    (devise de base du foyer V1).

    `carry_over_remainder` : flag **dormant** en E08 — stocké, **jamais lu** par
    le calcul de consommation. TODO : report du reliquat de période, E11+.

    `archived_at` : soft-delete (DELETE = archivage, S08.4 ; gabarit
    `Category.archived_at`).

    Invariant `scope=personal ⇒ 1 contributeur (owner)` /
    `scope=shared ⇒ ≥ 2 contributeurs` : **non** matérialisé en DB (contrainte
    multi-lignes inter-table) — appliqué au service S08.4 (y compris au
    **retrait** d'un contributeur : un `shared` ne doit pas tomber sous 2).

    Pas de FK `accounts` : un budget se rattache à catégorie + scope +
    contributeurs, pas à un compte (CONTEXT.md §Budget). L'isolation d'un
    budget `shared` (bucket PowerSync `account_shared_{account_id}`) est
    **dérivée au service** via les contributeurs (∩ membres du compte
    commun), non via une colonne `account_id` — frontière non matérialisée
    en DB, appliquée en S08.4 (RBAC + sync rules ; `scope` inattendu →
    fail-closed).
    """

    __tablename__ = "budgets"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    category_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "categories.id",
            ondelete="RESTRICT",
            name="fk_budgets_category_id_categories",
        ),
        nullable=False,
    )
    period_kind: Mapped[str] = mapped_column(String, nullable=False)
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    amount_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    scope: Mapped[str] = mapped_column(String, nullable=False)
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "users.id",
            ondelete="RESTRICT",
            name="fk_budgets_created_by_users",
        ),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    archived_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    carry_over_remainder: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("false"),
    )

    __table_args__ = (
        # Plein : couvre TOUTES les lignes (budgets archivés inclus) pour le
        # contrôle référentiel RESTRICT au DELETE d'une catégorie — un budget
        # archivé bloque toujours la suppression. Un index partiel ne pourrait
        # pas le servir (gabarit `ix_categories_parent_id`).
        Index("ix_budgets_category_id", "category_id"),
        # Plein : évite le seq-scan au DELETE/désactivation d'un user (RESTRICT).
        Index("ix_budgets_created_by", "created_by"),
        # Partiel actif : chemin « budgets actifs d'une catégorie » (S08.2/S08.3)
        # sur les seules lignes vivantes. `postgresql_where` byte-for-byte avec
        # la migration (parité create_all/Alembic — piège
        # `uq_invitations_pending_email`).
        Index(
            "ix_budgets_active",
            "category_id",
            postgresql_where=text("archived_at IS NULL"),
        ),
    )


class BudgetContributor(Base):
    """Un user qui contribue à un budget (CONTEXT.md §Budget : « liste de
    contributeurs »). Table d'association `(budget_id, user_id)`.

    `budget_id` `ON DELETE CASCADE` (le contributeur n'a aucun sens hors de son
    budget ; gabarit `account_members.account_id`). `user_id` `ON DELETE
    RESTRICT` (F02 — un user est désactivé, jamais supprimé). `unique
    (budget_id, user_id)` interdit le doublon ; le composite indexe `budget_id`
    (tête) → sert le CASCADE, donc seul `user_id` a un index standalone
    (gabarit `account_members`).
    """

    __tablename__ = "budget_contributors"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    budget_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "budgets.id",
            ondelete="CASCADE",
            name="fk_budget_contributors_budget_id_budgets",
        ),
        nullable=False,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "users.id",
            ondelete="RESTRICT",
            name="fk_budget_contributors_user_id_users",
        ),
        nullable=False,
    )

    __table_args__ = (
        # At most one membership per (budget, user). The composite also indexes
        # `budget_id` as its leading column → serves the CASCADE lookup, so no
        # standalone `budget_id` index is declared (gabarit `account_members`).
        UniqueConstraint(
            "budget_id",
            "user_id",
            name="uq_budget_contributors_budget_id_user_id",
        ),
        # `user_id` is not the leading column above → its own index is needed
        # for the `ON DELETE RESTRICT` seq-scan avoidance on `users` delete.
        Index("ix_budget_contributors_user_id", "user_id"),
    )


class BudgetThresholdAlert(Base):
    """Ligne d'idempotence d'une alerte de seuil déjà émise (S08.3, source de
    vérité de l'exactly-once des `BudgetThresholdEvent`). UNE ligne par
    `(budget, fenêtre de période, seuil %)` : sa présence atteste qu'un
    `BudgetThresholdEvent` a déjà été publié pour ce triplet — robuste au restart
    serveur et au rejeu (E13), vs un état « % avant/après » volatil.

    **Server-only** : table d'infra serveur, JAMAIS exposée aux règles de sync
    PowerSync (gabarit `users`/`admin_audit_logs`/`invitations`). Aucun client
    ne la lit ; le frontend recalcule l'état d'alerte via la consommation (S08.4).

    `budget_id` `ON DELETE CASCADE` (l'alerte n'a aucun sens hors de son budget ;
    gabarit `budget_contributors.budget_id`). `period_start` (`Date`) = borne
    basse de la fenêtre courante (`compute_period_window(...).start`).
    `threshold_pct` (`SmallInteger`) ∈ {80, 100, 120}, SANS CHECK (set verrouillé
    au domaine `crossed_thresholds`, gabarit `period_kind`/`scope`).
    Unique `(budget_id, period_start, threshold_pct)` nommée explicitement —
    cible de l'`ON CONFLICT ON CONSTRAINT` de l'INSERT idempotent.
    """

    __tablename__ = "budget_threshold_alerts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    budget_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "budgets.id",
            ondelete="CASCADE",
            name="fk_budget_threshold_alerts_budget_id_budgets",
        ),
        nullable=False,
    )
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    threshold_pct: Mapped[int] = mapped_column(SmallInteger, nullable=False)

    __table_args__ = (
        # Unique = idempotence ET cible de l'`ON CONFLICT ON CONSTRAINT`. Nom
        # littéral court et stable (déclaré identique côté migration, PAS `op.f`)
        # : la parité create_all/Alembic exige le même littéral des deux côtés
        # (même piège que `uq_invitations_pending_email`). `budget_id` en tête
        # sert le CASCADE → pas d'index `budget_id` standalone (gabarit
        # `budget_contributors`).
        UniqueConstraint(
            "budget_id",
            "period_start",
            "threshold_pct",
            name="uq_budget_threshold_alerts_dedup",
        ),
    )
