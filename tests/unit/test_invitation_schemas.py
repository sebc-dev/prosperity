"""Unit tests for the invitation Pydantic schemas (S04.4, P04.4.1).

The security-relevant pin here is structural: `InvitationResponse` must
never carry `token_hash`. Asserting on `model_fields` makes the guarantee
a property of the schema itself rather than an omission a future edit
could silently undo.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from backend.modules.auth.schemas import (
    InvitationCreatedResponse,
    InvitationCreateRequest,
    InvitationResponse,
)


def test_invitation_response_has_no_token_hash_field() -> None:
    # Structural guarantee (D4): `token_hash` is not a field, so FastAPI
    # filters it out even when the whole ORM row is returned.
    assert "token_hash" not in InvitationResponse.model_fields


def test_invitation_response_exposes_only_safe_fields() -> None:
    assert set(InvitationResponse.model_fields) == {
        "id",
        "email",
        "invited_at",
        "expires_at",
        "invited_by",
    }


def test_invitation_response_populates_from_attributes() -> None:
    # `from_attributes=True` lets FastAPI build the response straight from an
    # ORM row; a `token_hash` attribute on the source object is ignored.
    now = datetime.now(tz=UTC)
    source = SimpleNamespace(
        id=uuid.uuid4(),
        email="invite@example.com",
        invited_at=now,
        expires_at=now + timedelta(days=7),
        invited_by=uuid.uuid4(),
        token_hash="deadbeef" * 8,
    )

    resp = InvitationResponse.model_validate(source)

    assert resp.email == "invite@example.com"
    assert not hasattr(resp, "token_hash")


def test_invitation_create_request_rejects_malformed_email() -> None:
    with pytest.raises(ValidationError):
        InvitationCreateRequest(email="not-an-email")


def test_invitation_create_request_accepts_valid_email() -> None:
    req = InvitationCreateRequest(email="invite@example.com")
    assert req.email == "invite@example.com"


def test_invitation_created_response_has_no_token_hash_field() -> None:
    assert "token_hash" not in InvitationCreatedResponse.model_fields
    assert "token" in InvitationCreatedResponse.model_fields
    assert "accept_url" in InvitationCreatedResponse.model_fields
