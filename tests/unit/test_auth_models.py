"""Unit tests for auth ORM model behaviour that needs no DB (S04.3).

`Invitation._normalize_email` fires on attribute assignment (SQLAlchemy
`@validates`), so the lower+strip normalisation can be pinned without a
session — the same guarantee the functional `lower(email)` partial index
enforces at the database level (`test_invitations_constraint`).
"""

from __future__ import annotations

import uuid

from backend.modules.auth.models import Invitation


def test_invitation_email_is_normalized_on_assignment() -> None:
    inv = Invitation(email="  Alice@X.com  ", invited_by=uuid.uuid4())
    assert inv.email == "alice@x.com"
