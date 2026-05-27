"""Smoke test for FastAPI app boot (story S02.4).

Importing `backend.main` runs the router-include side effects. If a
chain of imports (transports → public → transports) ever circulates,
the import would fail at module load and this test would surface that
before any HTTP request is dispatched.
"""

from __future__ import annotations

from backend.main import app


def _paths() -> set[str]:
    return {getattr(route, "path", "") for route in app.routes}


def test_auth_routes_registered_on_app() -> None:
    paths = _paths()
    assert "/auth/login" in paths
    assert "/auth/refresh" in paths
    assert "/auth/logout" in paths


def test_healthz_route_still_registered() -> None:
    assert "/healthz" in _paths()
