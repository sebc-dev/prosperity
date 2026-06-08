"""Providers internes au module `banking` (parsers/lecteurs de sources externes).

Consommés cross-module **uniquement** via `banking.public` (contrat import-linter
4 : tout `backend` a interdiction d'importer `banking.providers`, seuls
`banking.public` et le futur `banking.service.polling` y ont accès). `OFXProvider`
(S12.2) est un parser fichier statique ; `EnableBankingProvider` (futur) sera un
pull-provider du Protocol `BankingProvider`.
"""

from __future__ import annotations
