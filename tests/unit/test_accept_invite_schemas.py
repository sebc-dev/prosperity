"""Unit tests for the accept-invite Pydantic schemas (S04.5, P04.5.4).

Pins the anti-poisoning contract of `AcceptInviteRequest` (`role`/`email`
in the body are silently dropped), its password floor (mirrors
`SetupRequest`), and the minimal `{email, expires_at}` shape of
`AcceptInvitePreviewResponse`.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import SecretStr, ValidationError

from backend.modules.auth.schemas import (
    AcceptInvitePreviewResponse,
    AcceptInviteRequest,
)


def _payload(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "token": "x" * 43,
        "display_name": "Invitee",
        "password": "correct-horse-battery-staple",
    }
    base.update(overrides)
    return base


def test_happy_path_parses_all_fields() -> None:
    req = AcceptInviteRequest(**_payload())  # type: ignore[arg-type]
    assert req.display_name == "Invitee"
    assert isinstance(req.password, SecretStr)
    assert req.password.get_secret_value() == "correct-horse-battery-staple"


def test_ignores_extra_role_and_email() -> None:
    # Anti-poisoning: a body carrying `role`/`email`/`id` parses fine but
    # those fields never materialise on the model — the route hardcodes
    # `member` and reads the email from the invitation.
    req = AcceptInviteRequest(
        **_payload(
            role="admin", email="attacker@evil.com", id="00000000-0000-0000-0000-000000000000"
        )  # type: ignore[arg-type]
    )
    assert not hasattr(req, "role")
    assert not hasattr(req, "email")
    assert not hasattr(req, "id")
    assert req.model_dump().keys() == {"token", "display_name", "password"}


def test_password_below_min_length_raises() -> None:
    with pytest.raises(ValidationError):
        AcceptInviteRequest(**_payload(password="x" * 11))  # type: ignore[arg-type]


def test_password_at_min_length_parses() -> None:
    AcceptInviteRequest(**_payload(password="x" * 12))  # type: ignore[arg-type]


def test_password_above_max_length_raises() -> None:
    with pytest.raises(ValidationError):
        AcceptInviteRequest(**_payload(password="x" * 129))  # type: ignore[arg-type]


def test_password_at_max_length_parses() -> None:
    AcceptInviteRequest(**_payload(password="x" * 128))  # type: ignore[arg-type]


def test_display_name_empty_raises() -> None:
    with pytest.raises(ValidationError):
        AcceptInviteRequest(**_payload(display_name=""))  # type: ignore[arg-type]


def test_display_name_above_max_raises() -> None:
    with pytest.raises(ValidationError):
        AcceptInviteRequest(**_payload(display_name="x" * 121))  # type: ignore[arg-type]


def test_token_missing_raises() -> None:
    with pytest.raises(ValidationError):
        AcceptInviteRequest(display_name="Invitee", password="x" * 12)  # type: ignore[call-arg]


def test_token_empty_raises() -> None:
    with pytest.raises(ValidationError):
        AcceptInviteRequest(**_payload(token=""))  # type: ignore[arg-type]


def test_token_above_max_raises() -> None:
    with pytest.raises(ValidationError):
        AcceptInviteRequest(**_payload(token="x" * 129))  # type: ignore[arg-type]


def test_password_is_secret_str_so_repr_does_not_leak() -> None:
    req = AcceptInviteRequest(**_payload(password="super-secret-12chars"))  # type: ignore[arg-type]
    assert "super-secret-12chars" not in repr(req)
    assert "super-secret-12chars" not in str(req.password)
    assert req.password.get_secret_value() == "super-secret-12chars"


def test_preview_response_shape() -> None:
    now = datetime.now(tz=UTC)
    resp = AcceptInvitePreviewResponse(email="invitee@example.com", expires_at=now)
    assert resp.model_dump().keys() == {"email", "expires_at"}
    assert resp.email == "invitee@example.com"
    assert resp.expires_at == now
