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
contract 2 forbids importing this module from outside `budget`.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import UUID, DateTime, ForeignKey, Index, String, func, text
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
