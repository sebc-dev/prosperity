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
    AutoValidationCriteria,
    BankingProviderError,
    BankTransaction,
    EncodingConfidence,
    EncodingDetectionError,
    ImportPreview,
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
from backend.modules.banking.service.import_ofx import analyze_import, compute_import_hash

# ⚠️ INV-S12.3-PREVIEW-ACCESS (D13) : `analyze_import` retourne une `ImportPreview`
# calculée sur des comptes internes BRUTS (non filtrés par accessibilité). Tout
# consommateur cross-module (route S12.4) DOIT gater chaque `external_ref` sur
# `accessible_account_ids(user_id)` avant exposition et rendre « lié-inaccessible »
# indistinguable de « non-lié » (non-disclosure). Cf. docstring `analyze_import`.

__all__ = [
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
]
