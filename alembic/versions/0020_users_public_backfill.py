"""users_public projection + trigger + backfill (E13 / S13.7 P13.7.5a)

Materialises `backend.modules.auth.models.UsersPublic` (#192) : la projection
NON-PII de `users` synchronisée au foyer (ADR 0003, glossaire §users_public).
Trois colonnes seulement — `{user_id, display_name, role}` — JAMAIS `email` ni
`password_hash` : la sync rule `household` la diffuse telle quelle, donc toute
colonne PII ajoutée ici fuiterait. `user_id` PK + FK `users.id ON DELETE CASCADE`
(la projection n'a aucun sens hors de son user) ; `role` réutilise l'enum PG
`user_role` existant (`create_type=False`).

Maintenue par un TRIGGER Postgres (D-UP, gabarit `admin_audit_logs` 0005) :
`sync_users_public()` upsert la projection à chaque INSERT/UPDATE de
`users.display_name` / `users.role`. Robuste à TOUT chemin d'écriture (même un
UPDATE SQL brut), zéro couplage au service auth, zéro arc import-linter. Le SQL
fonction+trigger est identique aux DDL `event.listen` du modèle (parité
create_all/Alembic — le test d'intégration installe le même trigger des deux
côtés). Backfill `INSERT ... SELECT` pour les users préexistants (users
désactivés inclus — leur nom reste nécessaire pour d'anciennes dettes).

Kept self-contained (no import from `models.py`) so a future model rename cannot
break a replay of this revision (gabarit `0007`..`0019`). PK/FK names are emitted
via `op.f(...)` to match the model's `NAMING_CONVENTION` output.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0020"
down_revision: str | Sequence[str] | None = "0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# The `user_role` PG enum already exists (created by 0002 for `users`). Reference
# it WITHOUT recreating (`create_type=False`) so `op.create_table` does not emit
# a duplicate `CREATE TYPE` (gabarit 0007 referencing the same enum).
_USER_ROLE = postgresql.ENUM("admin", "member", name="user_role", create_type=False)

# Function + trigger SQL — byte-for-byte the same projection logic as the
# `event.listen` DDL on `UsersPublic.__table__` (create_all/Alembic parity).
_FUNCTION_SQL = (
    "CREATE OR REPLACE FUNCTION sync_users_public() "
    "RETURNS trigger LANGUAGE plpgsql AS $$ "
    "BEGIN "
    "INSERT INTO users_public (user_id, display_name, role) "
    "VALUES (NEW.id, NEW.display_name, NEW.role) "
    "ON CONFLICT (user_id) DO UPDATE "
    "SET display_name = EXCLUDED.display_name, role = EXCLUDED.role; "
    "RETURN NEW; END; $$"
)
_TRIGGER_SQL = (
    "CREATE OR REPLACE TRIGGER trg_sync_users_public "
    "AFTER INSERT OR UPDATE OF display_name, role ON users "
    "FOR EACH ROW EXECUTE FUNCTION sync_users_public()"
)


def upgrade() -> None:
    op.create_table(
        "users_public",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("display_name", sa.String(length=120), nullable=False),
        sa.Column("role", _USER_ROLE, nullable=False),
        sa.PrimaryKeyConstraint("user_id", name=op.f("pk_users_public")),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_users_public_user_id_users"),
            ondelete="CASCADE",
        ),
    )
    op.execute(_FUNCTION_SQL)
    op.execute(_TRIGGER_SQL)
    # Backfill existing users (disabled ones included — their name still labels
    # old debts). The trigger covers every write FROM NOW ON; this seeds history.
    op.execute(
        "INSERT INTO users_public (user_id, display_name, role) "
        "SELECT id, display_name, role FROM users "
        "ON CONFLICT (user_id) DO NOTHING"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_sync_users_public ON users")
    op.execute("DROP FUNCTION IF EXISTS sync_users_public()")
    op.drop_table("users_public")  # drops its PK + the FK with it
