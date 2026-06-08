"""Public surface of the banking module — re-exports for cross-module use.

Seul module de `backend.modules.banking` importable par les pairs. Le contrat
`2-banking` interdit aux pairs d'atteindre `banking.{models,service,...}` ; les
re-exports ci-dessous sont **intra-module** (le contrat bride les *pairs*, pas
`public` lui-même) — aucune exception import-linter requise pour le domaine.

Exception : la re-export `OFXProvider`/`parse_ofx` traverse `banking.providers`,
interdit à tout `backend` par le contrat `4`. L'arc précis
`public -> providers.ofx` y est whitelisté (`ignore_imports`, cf. `.importlinter`).
"""

from __future__ import annotations

from backend.modules.banking.domain import (
    BankingProviderError,
    BankTransaction,
    EncodingConfidence,
    EncodingDetectionError,
    IncompatibleAccountError,
    ParsedOFX,
    ProviderUnavailableError,
)
from backend.modules.banking.providers.ofx import OFXProvider, parse_ofx
from backend.modules.banking.service.external_refs import (
    AccountAlreadyLinkedError,
    ExternalRefError,
    UnknownProviderError,
    find_internal_account,
    link,
)

__all__ = [
    "AccountAlreadyLinkedError",
    "BankTransaction",
    "BankingProviderError",
    "EncodingConfidence",
    "EncodingDetectionError",
    "ExternalRefError",
    "IncompatibleAccountError",
    "OFXProvider",
    "ParsedOFX",
    "ProviderUnavailableError",
    "UnknownProviderError",
    "find_internal_account",
    "link",
    "parse_ofx",
]
