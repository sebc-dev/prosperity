"""Unit tests for `backend.modules.accounts.schemas.SetupRequest` (S03.2).

Pins the four-field bootstrap form contract and the strict password
floor that differentiates `/setup` from `/auth/login`.
"""

from __future__ import annotations

import pytest
from pydantic import SecretStr, ValidationError

from backend.modules.accounts.schemas import SetupRequest


def _payload(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "email": "admin@example.com",
        "password": "correct-horse-battery-staple",
        "display_name": "Admin",
        "household_name": "Foyer Dupont",
    }
    base.update(overrides)
    return base


def test_setup_request_happy_path_parses_all_fields() -> None:
    req = SetupRequest(**_payload())  # type: ignore[arg-type]
    assert req.email == "admin@example.com"
    assert isinstance(req.password, SecretStr)
    assert req.password.get_secret_value() == "correct-horse-battery-staple"
    assert req.display_name == "Admin"
    assert req.household_name == "Foyer Dupont"


def test_password_below_min_length_raises() -> None:
    with pytest.raises(ValidationError):
        SetupRequest(**_payload(password="short"))  # type: ignore[arg-type]


def test_password_at_min_length_parses() -> None:
    SetupRequest(**_payload(password="x" * 12))  # type: ignore[arg-type]


def test_password_above_max_length_raises() -> None:
    with pytest.raises(ValidationError):
        SetupRequest(**_payload(password="x" * 129))  # type: ignore[arg-type]


def test_password_at_max_length_parses() -> None:
    SetupRequest(**_payload(password="x" * 128))  # type: ignore[arg-type]


def test_email_malformed_raises() -> None:
    with pytest.raises(ValidationError):
        SetupRequest(**_payload(email="not-an-email"))  # type: ignore[arg-type]


def test_display_name_empty_raises() -> None:
    with pytest.raises(ValidationError):
        SetupRequest(**_payload(display_name=""))  # type: ignore[arg-type]


def test_display_name_above_max_raises() -> None:
    with pytest.raises(ValidationError):
        SetupRequest(**_payload(display_name="x" * 121))  # type: ignore[arg-type]


def test_household_name_empty_raises() -> None:
    with pytest.raises(ValidationError):
        SetupRequest(**_payload(household_name=""))  # type: ignore[arg-type]


def test_household_name_above_max_raises() -> None:
    with pytest.raises(ValidationError):
        SetupRequest(**_payload(household_name="x" * 121))  # type: ignore[arg-type]


def test_password_is_secret_str_so_repr_does_not_leak() -> None:
    """`SecretStr` keeps the plaintext out of debug surfaces.

    Sentry tags, structlog bindings, FastAPI validator error traces, and
    `__repr__` outputs all consult `str(obj)` / `repr(obj)`. Pin that
    those never expose the raw password.
    """
    req = SetupRequest(**_payload(password="super-secret-12chars"))  # type: ignore[arg-type]
    assert "super-secret-12chars" not in repr(req)
    assert "super-secret-12chars" not in str(req.password)
    # The value is still accessible via the explicit getter.
    assert req.password.get_secret_value() == "super-secret-12chars"
