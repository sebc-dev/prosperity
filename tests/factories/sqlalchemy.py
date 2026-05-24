"""SQLAlchemy-backed factories for integration tests.

Populate this module as modules expose ORM models. The pattern (per
Stratégie de tests §10) is:

    class TransactionFactory(SQLAlchemyModelFactory):
        class Meta:
            model = Transaction
            sqlalchemy_session_persistence = "flush"

The async session wiring (factory.create called inside a sync wrapper
fed by `db_session`) is documented in Stratégie de tests §10.4.
"""

from __future__ import annotations

__all__: list[str] = []
