"""Public surface of the banking module — re-exports for cross-module use.

Seul module de `backend.modules.banking` importable par les pairs. Le contrat
`2-banking` interdit aux pairs d'atteindre `banking.{models,service,...}` ; les
re-exports ci-dessous sont **intra-module** (le contrat bride les *pairs*, pas
`public` lui-même) — aucune exception import-linter requise.
"""

from __future__ import annotations

from backend.modules.banking.service.external_refs import (
    AccountAlreadyLinkedError,
    ExternalRefError,
    UnknownProviderError,
    find_internal_account,
    link,
)

__all__ = [
    "AccountAlreadyLinkedError",
    "ExternalRefError",
    "UnknownProviderError",
    "find_internal_account",
    "link",
]
