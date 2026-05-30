"""Unit tests for `service.invitations` pure helpers (S04.3, no DB).

Pins the two DB-independent invariants the acceptance criteria fix: the
token hash is sha256 (glossary CONTEXT.md) and the TTL is 7 days.
"""

from __future__ import annotations

import hashlib
from datetime import timedelta

from backend.modules.auth.service.invitations import (
    INVITATION_TTL,
    hash_invitation_token,
)


def test_hash_is_sha256_hexdigest() -> None:
    # Fixed vector locks the algorithm itself, not just "matches sha256(x)".
    assert (
        hash_invitation_token("foo")
        == "2c26b46b68ffc68ff99b453c1d30413413422d706483bfa0f98a5e886266e7ae"
    )
    # And the general property, against the stdlib reference.
    assert hash_invitation_token("abc") == hashlib.sha256(b"abc").hexdigest()


def test_hash_is_64_hex_chars_and_deterministic() -> None:
    digest = hash_invitation_token("some-raw-token")
    assert len(digest) == 64
    assert all(c in "0123456789abcdef" for c in digest)
    assert digest == hash_invitation_token("some-raw-token")


def test_invitation_ttl_is_seven_days() -> None:
    assert INVITATION_TTL == timedelta(days=7)
