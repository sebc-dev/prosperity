"""debts + share_requests tables + activate dormant transactions FK (E09 socle)

Revision ID: 0014
Revises: 0013
Create Date: 2026-06-04

Materialises `backend.modules.debts.models.{Debt,ShareRequest}` (S09.1, #142)
and activates the dormant FK `transactions.share_request_id → share_requests.id`
laid nullable (without a FK) in S07.4 / 0010.

**Ordre explicite** (les FK dictent l'ordre) :
  (1) `share_requests` — porte la FK `source_transaction_id → transactions.id`
      `CASCADE` (transactions existe depuis 0009) + l'unique partiel actif ;
  (2) `debts` — FK `account_id → accounts.id` `RESTRICT`,
      `source_transaction_id → transactions.id` `CASCADE`, `*_user_id → users`
      `RESTRICT`, deux CHECK défensifs ;
  (3) `op.create_foreign_key` activant `transactions.share_request_id →
      share_requests.id` `SET NULL`. La colonne est **déjà posée nullable en
      0010** → PAS de `add_column`, juste la contrainte.

La FK `transactions ↔ share_requests` est circulaire, mais les deux colonnes
sont nullable et la contrainte transactions→share_requests est ajoutée APRÈS
les deux tables (ALTER) → pas de cycle bloquant. `downgrade()` retire cette FK
dormante AVANT de droper les tables.

`origin` (debts) est un `VARCHAR` SANS CHECK (set fermé verrouillé au boundary
Pydantic S09.3 ; gabarit `transactions.state`/`budgets.scope`). Les CHECK
défensifs portent uniquement sur l'anti auto-dette et le montant positif.

Kept self-contained (no import from `models.py`) so a future model rename
cannot break a replay of this revision (gabarit `0009`..`0013`). Les littéraux
`'shared_account_overflow'` etc. ne sont pas dupliqués ici (aucun CHECK sur
`origin`).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0014"
down_revision: str | Sequence[str] | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # (1) share_requests — l'acte explicite de partage (direction canonique du
    # lien vers la tx). Créée AVANT debts, et avant l'activation de la FK
    # dormante de transactions qui la cible.
    op.create_table(
        "share_requests",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_transaction_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("requested_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("requested_from", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ratio", sa.Numeric(precision=5, scale=4), nullable=False),
        sa.Column("short_label", sa.String(length=100), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_share_requests")),
        sa.ForeignKeyConstraint(
            ["source_transaction_id"],
            ["transactions.id"],
            name=op.f("fk_share_requests_source_transaction_id_transactions"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["requested_by"],
            ["users.id"],
            name=op.f("fk_share_requests_requested_by_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["requested_from"],
            ["users.id"],
            name=op.f("fk_share_requests_requested_from_users"),
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "requested_by <> requested_from",
            name=op.f("ck_share_requests_no_self"),
        ),
    )
    # Literal index names (not op.f) to match the model's `Index(...)` names
    # exactly — the create_all/Alembic parity the snapshot pins. The unique
    # partial index forbids two ACTIVE share requests on the same (tx, débiteur)
    # pair; `postgresql_where` must match the model byte-for-byte (same trap as
    # `uq_invitations_pending_email`).
    op.create_index(
        "uq_share_requests_active",
        "share_requests",
        ["source_transaction_id", "requested_from"],
        unique=True,
        postgresql_where=sa.text("revoked_at IS NULL"),
    )
    op.create_index(
        "ix_share_requests_requested_from", "share_requests", ["requested_from"], unique=False
    )
    op.create_index(
        "ix_share_requests_requested_by", "share_requests", ["requested_by"], unique=False
    )

    # (2) debts — la projection serveur (ADR 0002).
    op.create_table(
        "debts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("from_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("to_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("amount_cents", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_transaction_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("origin", sa.String(), nullable=False),
        sa.Column("share_ratio", sa.Numeric(precision=5, scale=4), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("materialization_trace", sa.String(), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_debts")),
        sa.ForeignKeyConstraint(
            ["from_user_id"],
            ["users.id"],
            name=op.f("fk_debts_from_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["to_user_id"],
            ["users.id"],
            name=op.f("fk_debts_to_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["accounts.id"],
            name=op.f("fk_debts_account_id_accounts"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["source_transaction_id"],
            ["transactions.id"],
            name=op.f("fk_debts_source_transaction_id_transactions"),
            ondelete="CASCADE",
        ),
        # Défensifs : anti auto-dette + montant strictement positif (gabarit
        # `ck_transactions_debt_generation_override`, set fermé hors Pydantic).
        sa.CheckConstraint("from_user_id <> to_user_id", name=op.f("ck_debts_no_self_debt")),
        sa.CheckConstraint("amount_cents > 0", name=op.f("ck_debts_amount_positive")),
    )
    op.create_index("ix_debts_from_user_id", "debts", ["from_user_id"], unique=False)
    op.create_index("ix_debts_to_user_id", "debts", ["to_user_id"], unique=False)
    op.create_index(
        "ix_debts_source_transaction_id", "debts", ["source_transaction_id"], unique=False
    )

    # (3) Activation de la FK dormante (colonne déjà posée nullable en 0010).
    # `SET NULL` : révoquer/supprimer une SR ne supprime pas la tx — son handle
    # `share_request_id` est remis à NULL. Ajoutée par ALTER après les deux
    # tables → casse le cycle transactions ↔ share_requests (jumeau du
    # `use_alter=True` côté ORM).
    op.create_foreign_key(
        op.f("fk_transactions_share_request_id_share_requests"),
        "transactions",
        "share_requests",
        ["share_request_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    # Retirer la FK dormante AVANT de droper les tables (sinon le drop de
    # share_requests est refusé par la contrainte encore vivante).
    op.drop_constraint(
        op.f("fk_transactions_share_request_id_share_requests"),
        "transactions",
        type_="foreignkey",
    )
    op.drop_index("ix_debts_source_transaction_id", table_name="debts")
    op.drop_index("ix_debts_to_user_id", table_name="debts")
    op.drop_index("ix_debts_from_user_id", table_name="debts")
    op.drop_table("debts")  # drops its FKs + CHECKs with it
    op.drop_index("ix_share_requests_requested_by", table_name="share_requests")
    op.drop_index("ix_share_requests_requested_from", table_name="share_requests")
    op.drop_index("uq_share_requests_active", table_name="share_requests")
    op.drop_table("share_requests")  # drops its FKs + CHECK with it
