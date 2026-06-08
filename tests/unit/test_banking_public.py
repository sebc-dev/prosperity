"""Unit tests for `backend.modules.banking.public` cross-module surface (S12.1, P12.1.2).

Pins the exact `__all__`, the re-export identities (guards against a refactor that
re-implements a stub in `public.py` instead of re-exporting the real symbols), and
the error-family subclassing the route boundary (S12.4) relies on for a single
`except ExternalRefError`. Gabarit `test_transactions_public.py`.
"""

from __future__ import annotations

import backend.modules.banking.public as banking_public
from backend.modules.banking.public import (
    AccountAlreadyLinkedError,
    ExternalRefError,
    UnknownProviderError,
    find_internal_account,
    link,
)
from backend.modules.banking.service import external_refs as _external_refs

_EXPECTED = {
    "AccountAlreadyLinkedError",
    "ExternalRefError",
    "UnknownProviderError",
    "find_internal_account",
    "link",
}


def test_public_exports_exact_set() -> None:
    assert set(banking_public.__all__) == _EXPECTED


def test_reexport_identities() -> None:
    # Each symbol IS the re-exported identity (guards against a re-implemented stub).
    assert find_internal_account is _external_refs.find_internal_account
    assert link is _external_refs.link
    assert ExternalRefError is _external_refs.ExternalRefError
    assert UnknownProviderError is _external_refs.UnknownProviderError
    assert AccountAlreadyLinkedError is _external_refs.AccountAlreadyLinkedError


def test_error_family_subclassing() -> None:
    # Load-bearing for the future single `except ExternalRefError` at the S12.4 boundary.
    assert issubclass(UnknownProviderError, ExternalRefError)
    assert issubclass(AccountAlreadyLinkedError, ExternalRefError)
