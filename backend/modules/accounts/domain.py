"""Pure domain values for the accounts module (no SQLAlchemy dependency).

Holds the persistence-independent value catalogue of the module. In
S05.1 that is the `AccountType` enum; S05.2 adds the pure `AccountValidator`
(currency / owner-XOR-members / Σ share_ratio rules) here, which is why
the enum lives in `domain.py` rather than `models.py` — the validator must
reason about account types without importing the ORM stack.

Internal to `modules.accounts`: cross-module callers reach domain values
through `backend.modules.accounts.public`. Import-linter forbids reaching
into `backend.modules.accounts.domain` directly from peer modules.
"""

from __future__ import annotations

import enum


class AccountType(enum.StrEnum):
    """Financial account categories (F02).

    Mirrored by the Postgres `account_type` ENUM (Alembic 0007). Adding a
    value requires a migration that ALTERs that type. `StrEnum` gives
    runtime enforcement on assignment plus a single source of truth for
    the Pydantic transports landing in S05.3.

    The SQLAlchemy mapping lives in `models.py`
    (`mapped_column(Enum(AccountType, name="account_type",
    values_callable=_account_type_values))`); `values_callable` keeps the
    stored values (`"courant"`…) aligned with the PG ENUM rather than the
    member *names*. A round-trip integration test (P05.1.3) pins that.
    """

    COURANT = "courant"
    LIVRET = "livret"
    EPARGNE = "epargne"
    ESPECES = "especes"
    CREDIT = "credit"
