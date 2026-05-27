"""Shared SQLAlchemy declarative base for every module's ORM models.

`Base` lives in `shared/` because every persisted module attaches its
tables to the **same** `MetaData`. A single metadata makes
`create_all()` (test fixtures) and `alembic.env.target_metadata`
trivially correct without aggregator tricks, lets cross-module FKs
(E04+ once `users` references `household`) declare cleanly without
metadata reconciliation, and keeps the naming convention in one place.

Import-linter contract 3 (`shared` imports nothing from `modules`)
holds: this module only imports from SQLAlchemy.

The explicit naming convention is required so constraints created via
`create_all()` match the names Alembic produces via `op.f(...)`.
Without this, a future `alembic revision --autogenerate` would diff
every constraint and emit noisy renames.
"""

from __future__ import annotations

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_label)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Declarative base shared by every module's ORM models."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)
