"""Fixtures for the E2E API tier.

Intentionally empty for now: the real-commit stack (`committed_client`,
`committed_sessionmaker`, `_clean_committed_db`, `postgres_container`)
is inherited from the root `tests/conftest.py` (P-E2E.1 hoist). This
module exists to anchor the package and host any future e2e-only
overrides without disturbing the shared fixtures.
"""

from __future__ import annotations
