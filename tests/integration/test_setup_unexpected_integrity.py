"""Pin the SQLSTATE-based DBAPIError discrimination on POST /setup.

Race-lost SQLSTATEs collapse to 404:
  * 23505 unique_violation (PK on household, UNIQUE on lower(email))
  * 23514 check_violation (singleton CHECK)
  * 40001 serialization_failure (REPEATABLE READ concurrent flush)

Anything else — NOT NULL (23502), FK (23503), absent sqlstate — re-raises
so an application bug surfaces as 500 instead of being masked as
"setup locked".

httpx's `ASGITransport` defaults `raise_app_exceptions=True`, so an
unhandled exception in the route propagates through `await client.post`
in tests; in prod Starlette's `ServerErrorMiddleware` catches the same
exception and converts it to 500. We pin both shapes:

* race-lost SQLSTATEs → `await client.post` returns 404 cleanly.
* every other SQLSTATE → `await client.post` raises, proving the route
  did not silently swallow the bug.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from httpx import AsyncClient
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession


def _setup_payload(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "email": "admin@example.com",
        "password": "correct-horse-battery-staple",
        "display_name": "Admin",
        "household_name": "Foyer Test",
    }
    base.update(overrides)
    return base


def _integrity_error_with_sqlstate(sqlstate: str | None) -> IntegrityError:
    """Build an `IntegrityError` whose `.orig.sqlstate` matches the input.

    The route reads `getattr(exc.orig, "sqlstate", None)`; we forge an
    `orig` object that satisfies that attribute access without going
    through psycopg/asyncpg to provoke a real violation.
    """
    if sqlstate is None:
        fake_orig: object = object()  # no sqlstate attribute at all
    else:
        fake_orig = type("PgError", (), {"sqlstate": sqlstate})()
    return IntegrityError("forged", params=None, orig=fake_orig)  # type: ignore[arg-type]


def _dbapi_error_with_sqlstate(sqlstate: str) -> DBAPIError:
    """Build a `DBAPIError` (not the `IntegrityError` subclass) for 40001.

    Postgres raises serialization_failure under REPEATABLE READ as a
    plain `DBAPIError`, not as an `IntegrityError`. Forging this shape
    proves the route's `except DBAPIError` catches the parent class.
    """
    fake_orig = type("PgError", (), {"sqlstate": sqlstate})()
    return DBAPIError("forged", params=None, orig=fake_orig)  # type: ignore[arg-type]


async def test_post_setup_propagates_not_null_violation(
    async_client: AsyncClient,
    auth_schema: AsyncSession,  # noqa: ARG001
) -> None:
    """23502 NOT NULL violation = app bug → re-raise (→ 500 in prod), never 404."""
    exc = _integrity_error_with_sqlstate("23502")

    async def _explode(*_args: object, **_kwargs: object) -> None:
        raise exc

    with patch(
        "backend.modules.accounts.transports.http.initialize_bootstrap",
        side_effect=_explode,
    ):
        with pytest.raises(IntegrityError):
            await async_client.post("/setup", json=_setup_payload())


async def test_post_setup_unique_violation_collapses_to_404(
    async_client: AsyncClient,
    auth_schema: AsyncSession,  # noqa: ARG001
) -> None:
    """23505 unique_violation = race lost on PK or email → 404."""
    exc = _integrity_error_with_sqlstate("23505")

    async def _explode(*_args: object, **_kwargs: object) -> None:
        raise exc

    with patch(
        "backend.modules.accounts.transports.http.initialize_bootstrap",
        side_effect=_explode,
    ):
        resp = await async_client.post("/setup", json=_setup_payload())

    assert resp.status_code == 404


async def test_post_setup_check_violation_collapses_to_404(
    async_client: AsyncClient,
    auth_schema: AsyncSession,  # noqa: ARG001
) -> None:
    """23514 check_violation = singleton CHECK lost → 404."""
    exc = _integrity_error_with_sqlstate("23514")

    async def _explode(*_args: object, **_kwargs: object) -> None:
        raise exc

    with patch(
        "backend.modules.accounts.transports.http.initialize_bootstrap",
        side_effect=_explode,
    ):
        resp = await async_client.post("/setup", json=_setup_payload())

    assert resp.status_code == 404


async def test_post_setup_serialization_failure_collapses_to_404(
    async_client: AsyncClient,
    auth_schema: AsyncSession,  # noqa: ARG001
) -> None:
    """40001 serialization_failure = REPEATABLE READ race-lost → 404.

    Postgres raises 40001 as `DBAPIError`, not `IntegrityError`. The
    route catches the parent class and treats this as race-lost
    semantics (same as 23505).
    """
    exc = _dbapi_error_with_sqlstate("40001")

    async def _explode(*_args: object, **_kwargs: object) -> None:
        raise exc

    with patch(
        "backend.modules.accounts.transports.http.initialize_bootstrap",
        side_effect=_explode,
    ):
        resp = await async_client.post("/setup", json=_setup_payload())

    assert resp.status_code == 404


async def test_post_setup_integrity_error_without_sqlstate_propagates(
    async_client: AsyncClient,
    auth_schema: AsyncSession,  # noqa: ARG001
) -> None:
    """An `exc.orig` without `.sqlstate` is treated as unknown → re-raise.

    Guards against drivers that don't expose `sqlstate` consistently
    (e.g. a future swap to a different async driver). `getattr(...)`
    returns None, which is not in `_RACE_LOST_SQLSTATES`, so the route
    re-raises and Starlette's `ServerErrorMiddleware` emits 500 in
    prod.
    """
    exc = _integrity_error_with_sqlstate(None)

    async def _explode(*_args: object, **_kwargs: object) -> None:
        raise exc

    with patch(
        "backend.modules.accounts.transports.http.initialize_bootstrap",
        side_effect=_explode,
    ):
        with pytest.raises(IntegrityError):
            await async_client.post("/setup", json=_setup_payload())
