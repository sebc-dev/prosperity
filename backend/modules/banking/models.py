"""ORM models for the banking module (E12 socle persisté).

Premier internal du module banking (qui n'avait que `__init__.py` +
`public.py`). `models.py` est du SQLA **pur** : la validation de `provider`
et le rejet du double-lien vivent dans `service/external_refs.py` (S12.1.2),
pas ici (gabarit `transactions.models` ↔ `transactions.service`).

`BankAccountExternalRef` matérialise le mapping persistant « compte externe
(réf. du fichier OFX) → compte interne » (CONTEXT.md §Import OFX). Réutilisable
par Enable Banking plus tard via `provider` text — d'où PAS d'ENUM DB.

Layering (ADR 0005, contrat 1) : `banking` est au-dessus d'`accounts` (même
couche que `transactions`/`budget`). La FK vers `accounts` est déclarée **par
chaîne** (`ForeignKey("accounts.id")`), résolue au runtime par SQLAlchemy SANS
import Python de `Account` — aucune nouvelle exception import-linter.

Surface publique : importable seulement depuis `banking` (contrat `2-banking` ;
`banking.models` listé en `forbidden_modules` des contrats pairs).
"""

from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import (
    UUID,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from backend.shared.models import Base


class BankAccountExternalRef(Base):
    """Lien persistant entre une référence de compte externe (issue d'un
    fichier OFX, ex. numéro masqué) et un compte interne du foyer.

    `external_ref` : identifiant du compte tel que désigné par la source
    externe (texte opaque). `provider` : `'ofx'` en V1, `'enable_banking'`
    plus tard — text, pas ENUM (set ouvert/évolutif ; un ENUM imposerait un
    `ALTER TYPE` par provider). PAS de `CheckConstraint` (contrairement aux
    sets *fermés* `leg_role`/`debt_generation_override`) : le verrou de
    valeurs vit au boundary service (gabarit `Account.currency`/`state`).

    Unicité composite `(external_ref, provider)` : la même réf sous deux
    providers distincts cohabite — jamais d'unicité sur `external_ref` seul.

    `internal_account_id` : FK → `accounts` en `ON DELETE RESTRICT` (un compte
    n'est jamais hard-deleted, F02). PAS de création de compte ici — le service
    ne fait que *lier* un compte existant.
    """

    __tablename__ = "bank_account_external_refs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    external_ref: Mapped[str] = mapped_column(String, nullable=False)
    internal_account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "accounts.id",
            ondelete="RESTRICT",
            name="fk_bank_account_external_refs_internal_account_id_accounts",
        ),
        nullable=False,
    )
    provider: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        # Unicité composite : `external_ref` en tête → l'index unique dessert
        # AUSSI le lookup `find_internal_account(external_ref, provider)`.
        UniqueConstraint(
            "external_ref",
            "provider",
            name="uq_bank_account_external_refs_external_ref_provider",
        ),
        # FK RESTRICT indexée (gabarit `ix_transactions_account_id`) : évite le
        # seq-scan sur un delete parent + dessert le reverse-lookup par compte.
        Index(
            "ix_bank_account_external_refs_internal_account_id",
            "internal_account_id",
        ),
    )
