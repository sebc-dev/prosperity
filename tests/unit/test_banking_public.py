"""Unit tests for `backend.modules.banking.public` cross-module surface (S12.1/S12.2).

Pins the exact `__all__`, the re-export identities (guards against a refactor that
re-implements a stub in `public.py` instead of re-exporting the real symbols), and
the error-family subclassing the route boundary (S12.4) relies on for single
`except` blocks. Gabarit `test_transactions_public.py`.
"""

from __future__ import annotations

import backend.modules.banking.public as banking_public
from backend.modules.banking.domain import (
    AutoValidationCriteria,
    BankingProviderError,
    BankTransaction,
    EncodingDetectionError,
    ImportPreview,
    IncompatibleAccountError,
    ParsedOFX,
    ProviderUnavailableError,
)
from backend.modules.banking.providers import ofx as _ofx
from backend.modules.banking.public import (
    AccountAlreadyLinkedError,
    ExternalRefError,
    OFXProvider,
    UnknownProviderError,
    find_internal_account,
    link,
    parse_ofx,
)
from backend.modules.banking.public import (
    IncompatibleAccountError as PublicIncompatibleAccountError,
)
from backend.modules.banking.service import external_refs as _external_refs
from backend.modules.banking.service import import_ofx as _import_ofx

_EXPECTED = {
    "AccountAlreadyLinkedError",
    "AutoValidationCriteria",
    "BankTransaction",
    "BankingProviderError",
    "EncodingConfidence",
    "EncodingDetectionError",
    "ExternalRefError",
    "ImportPreview",
    "IncompatibleAccountError",
    "OFXProvider",
    "ParsedOFX",
    "ProviderUnavailableError",
    "UnknownProviderError",
    "analyze_import",
    "compute_import_hash",
    "find_internal_account",
    "link",
    "parse_ofx",
}


def test_public_exports_exact_set() -> None:
    assert set(banking_public.__all__) == _EXPECTED


def test_reexport_identities_external_refs() -> None:
    assert find_internal_account is _external_refs.find_internal_account
    assert link is _external_refs.link
    assert ExternalRefError is _external_refs.ExternalRefError
    assert UnknownProviderError is _external_refs.UnknownProviderError
    assert AccountAlreadyLinkedError is _external_refs.AccountAlreadyLinkedError


def test_reexport_identities_ofx() -> None:
    # Each symbol IS the re-exported identity (guards against a re-implemented stub).
    assert OFXProvider is _ofx.OFXProvider
    assert parse_ofx is _ofx.parse_ofx
    assert banking_public.BankTransaction is BankTransaction
    assert banking_public.ParsedOFX is ParsedOFX
    assert banking_public.BankingProviderError is BankingProviderError
    assert PublicIncompatibleAccountError is IncompatibleAccountError


def test_reexport_identities_import_ofx() -> None:
    # Same function/object identity, not just importable (review Tests n3).
    assert banking_public.analyze_import is _import_ofx.analyze_import
    assert banking_public.compute_import_hash is _import_ofx.compute_import_hash
    assert banking_public.ImportPreview is ImportPreview
    assert banking_public.AutoValidationCriteria is AutoValidationCriteria


def test_error_family_subclassing_external_refs() -> None:
    assert issubclass(UnknownProviderError, ExternalRefError)
    assert issubclass(AccountAlreadyLinkedError, ExternalRefError)


def test_error_family_subclassing_provider() -> None:
    # Load-bearing for the single `except BankingProviderError` at the S12.4 boundary.
    assert issubclass(IncompatibleAccountError, BankingProviderError)
    assert issubclass(ProviderUnavailableError, BankingProviderError)
    assert issubclass(EncodingDetectionError, BankingProviderError)
