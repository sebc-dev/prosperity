"""Unit tests for `backend.modules.auth.public` cross-module surface (S02.2 + S02.4)."""

from __future__ import annotations

import backend.modules.auth.public as auth_public
from backend.modules.auth.models import User as _user_model
from backend.modules.auth.public import (
    ExpiredTokenError,
    InvalidTokenError,
    User,
    get_current_user,
    issue_access_token,
    verify_access_token,
)
from backend.modules.auth.service import jwt as _jwt_service
from backend.modules.auth.transports import dependencies as _deps


def test_public_exports_exact_set() -> None:
    assert set(auth_public.__all__) == {
        "issue_access_token",
        "verify_access_token",
        "InvalidTokenError",
        "ExpiredTokenError",
        "User",
        "get_current_user",
    }


def test_public_symbols_are_callable_or_exceptions() -> None:
    assert callable(issue_access_token)
    assert callable(verify_access_token)
    assert callable(get_current_user)
    assert issubclass(InvalidTokenError, Exception)
    assert issubclass(ExpiredTokenError, InvalidTokenError)
    assert isinstance(User, type)


def test_public_names_are_identical_objects_to_internals() -> None:
    # Guards against a refactor that re-implements a stub in `public.py`
    # instead of re-exporting the real symbols from internal modules.
    assert auth_public.issue_access_token is _jwt_service.issue_access_token
    assert auth_public.verify_access_token is _jwt_service.verify_access_token
    assert auth_public.InvalidTokenError is _jwt_service.InvalidTokenError
    assert auth_public.ExpiredTokenError is _jwt_service.ExpiredTokenError
    assert auth_public.User is _user_model
    assert auth_public.get_current_user is _deps.get_current_user
