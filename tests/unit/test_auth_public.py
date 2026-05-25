"""Unit tests for `backend.modules.auth.public` cross-module surface (S02.2)."""

from __future__ import annotations

import backend.modules.auth.public as auth_public
from backend.modules.auth.public import (
    ExpiredTokenError,
    InvalidTokenError,
    issue_access_token,
    verify_access_token,
)


def test_public_exports_exactly_four_names() -> None:
    assert set(auth_public.__all__) == {
        "issue_access_token",
        "verify_access_token",
        "InvalidTokenError",
        "ExpiredTokenError",
    }


def test_public_symbols_are_callable_or_exceptions() -> None:
    # Sanity check that the re-exported names are the real objects, not stubs.
    assert callable(issue_access_token)
    assert callable(verify_access_token)
    assert issubclass(InvalidTokenError, Exception)
    assert issubclass(ExpiredTokenError, InvalidTokenError)
