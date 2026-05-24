"""Test factories.

Two flavours live side-by-side:

- `sqlalchemy.py`  — `factory.alchemy.SQLAlchemyModelFactory` subclasses
  bound to a session, used in integration tests that need persisted
  rows (cf. Stratégie de tests §10).
- `domain.py`      — pure-Python builders for value objects / domain
  entities, used in unit tests that must not touch SQLA.

Both modules are empty skeletons until the relevant modules ship their
models.
"""
