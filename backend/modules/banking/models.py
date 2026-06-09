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


class ImportedTransaction(Base):
    """Journal de dedup des lignes importées (E12 / S12.3 P12.3.1).

    Une ligne par transaction bancaire effectivement *commitée* (S12.4.3) :
    `import_hash` = sha256 composite `(account_id, date, amount_cents,
    libellé_normalisé)` (FITID JAMAIS utilisé, doctrine F04). L'unicité de
    `import_hash` porte l'idempotence du commit ; en S12.3 la table est lue
    seule (`analyze_import` calcule `duplicate_count`), jamais écrite.

    `source` : `'ofx'` en V1, `'enable_banking'` plus tard — text (set ouvert,
    pas d'ENUM, gabarit `BankAccountExternalRef.provider`). FK → `accounts`
    déclarée par chaîne (banking au-dessus d'accounts, contrat 1) en
    `ON DELETE RESTRICT` (F02 : pas de hard-delete de compte).

    ⚠️ Nommage : `account_id` désigne le **compte INTERNE** (même sémantique
    que `BankAccountExternalRef.internal_account_id`) ; le nom court suit la
    lettre de l'AC #178 (`imported_transactions.account_id`). Les deux tables
    sœurs pointent `accounts` — ne pas confondre les deux conventions de nom.
    """

    __tablename__ = "imported_transactions"

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
            name="fk_imported_transactions_account_id_accounts",
        ),
        nullable=False,
    )
    import_hash: Mapped[str] = mapped_column(String, nullable=False)
    imported_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    source: Mapped[str] = mapped_column(String, nullable=False)

    __table_args__ = (
        UniqueConstraint("import_hash", name="uq_imported_transactions_import_hash"),
        Index("ix_imported_transactions_account_id", "account_id"),
    )
