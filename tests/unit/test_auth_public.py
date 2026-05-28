"""Unit tests for `backend.modules.auth.public` cross-module surface.

Covers S02.2 + S02.4 (jwt + transports) and S03.2 (user creation +
auto-login symbols re-exported for `accounts.transports.http`).
"""

from __future__ import annotations

import backend.modules.auth.public as auth_public
from backend.modules.auth.models import User as _user_model
from backend.modules.auth.models import UserRole as _user_role_enum
from backend.modules.auth.public import (
    ExpiredTokenError,
    InvalidTokenError,
    TokenPair,
    User,
    UserRole,
    any_user_exists,
    create_user,
    get_current_user,
    issue_access_token,
    issue_refresh_token,
    sanitize_device_label,
    verify_access_token,
)
from backend.modules.auth.schemas import TokenPair as _schemas_token_pair
from backend.modules.auth.schemas import sanitize_device_label as _schemas_sanitize
from backend.modules.auth.service import jwt as _jwt_service
from backend.modules.auth.service import refresh_tokens as _refresh_service
from backend.modules.auth.service import users as _users_service
from backend.modules.auth.transports import dependencies as _deps


def test_public_exports_exact_set() -> None:
    # Pinning the exact set surfaces accidental additions/removals in
    # review — any change here forces a deliberate discussion of
    # cross-module surface expansion.
    assert set(auth_public.__all__) == {
        "ExpiredTokenError",
        "InvalidTokenError",
        "TokenPair",
        "User",
        "UserRole",
        "any_user_exists",
        "create_user",
        "get_current_user",
        "issue_access_token",
        "issue_refresh_token",
        "sanitize_device_label",
        "verify_access_token",
    }


def test_public_symbols_are_callable_or_exceptions() -> None:
    assert callable(issue_access_token)
    assert callable(verify_access_token)
    assert callable(issue_refresh_token)
    assert callable(create_user)
    assert callable(any_user_exists)
    assert callable(get_current_user)
    assert callable(sanitize_device_label)
    assert issubclass(InvalidTokenError, Exception)
    assert issubclass(ExpiredTokenError, InvalidTokenError)
    assert isinstance(User, type)
    assert isinstance(UserRole, type)
    assert isinstance(TokenPair, type)


def test_public_names_are_identical_objects_to_internals() -> None:
    # Guards against a refactor that re-implements a stub in `public.py`
    # instead of re-exporting the real symbols from internal modules.
    assert auth_public.issue_access_token is _jwt_service.issue_access_token
    assert auth_public.verify_access_token is _jwt_service.verify_access_token
    assert auth_public.InvalidTokenError is _jwt_service.InvalidTokenError
    assert auth_public.ExpiredTokenError is _jwt_service.ExpiredTokenError
    assert auth_public.issue_refresh_token is _refresh_service.issue
    assert auth_public.create_user is _users_service.create_user
    assert auth_public.any_user_exists is _users_service.any_user_exists
    assert auth_public.TokenPair is _schemas_token_pair
    assert auth_public.sanitize_device_label is _schemas_sanitize
    assert auth_public.User is _user_model
    assert auth_public.UserRole is _user_role_enum
    assert auth_public.get_current_user is _deps.get_current_user
