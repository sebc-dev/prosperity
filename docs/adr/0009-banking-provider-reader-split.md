# Banking : séparation `BankingProvider` (polling-only) / `BankingReader` (cache)

L'architecture décrit le module `banking` comme la "porte de sortie" si Enable Banking devient indisponible, et F14 impose que *"les tools MCP ne déclenchent jamais un appel synchrone à Enable Banking"*. Pour matérialiser ces deux contraintes dans le code (pas juste en convention), nous décidons d'exposer **deux Protocols distincts** dans `modules/banking/public.py` :

- **`BankingProvider`** : Protocol pull-only à 3 méthodes (`list_accounts`, `fetch_transactions`, `consent_status`), implémenté par `EnableBankingProvider`, `OFXProvider`, `MockProvider`. Erreurs = hiérarchie d'exceptions typées (`ConsentExpiredError`, `ConsentRevokedError`, `ProviderUnavailableError`, `RateLimitedError`, `IncompatibleAccountError`). **Instancié et appelé uniquement par le job de polling interne au module `banking`.**
- **`BankingReader`** : Protocol de lecture synchrone depuis la DB locale (`get_account`, `list_recent_transactions`, `last_sync_at`). **Seule interface autorisée** pour tous les consommateurs cross-module (reconciliation, MCP, dashboard freshness indicator).

Un contrat import-linter additionnel interdit l'import de `BankingProvider` en dehors de `modules.banking.service.polling`.

## Considered Options

- **Une seule interface** : oblige les consommateurs à savoir s'ils déclenchent un appel réseau ou une lecture cache → casse F14 en pratique.
- **Result type au lieu d'exceptions** : ergonomie Python moins idiomatique, sans bénéfice tangible solo.
- **Push/webhook** : Enable Banking ne le propose pas ; OFX n'en a pas par nature.

## Consequences

- Le changement de provider (Enable Banking → BudgetInsight, OFX-only, etc.) ne touche aucun consommateur en dehors du module `banking`.
- `last_sync_at` est exposé par `BankingReader`, permettant un indicateur de fraîcheur ("synced il y a 4h") sur le dashboard sans logique dupliquée. Warning UI subtil au-delà de 12h.
- Les tests contract (test strategy §4.7) s'appliquent au seul `BankingProvider` ; les autres modules sont testés contre `MockBankingReader` simple.
- Décision dépendante de l'ADR 0005 (graphe directionnel / public surface).

> **Amendement 2026-06-08 (S12.2, issue #177).** `OFXProvider` est finalement un **parser fichier statique synchrone** (`parse(file_bytes) → ParsedOFX`), **PAS** une implémentation du Protocol pull-only `BankingProvider` : OFX n'a ni polling, ni consentement, ni async réseau. L'implémenteur OFX du Protocol décrit ci-dessus **n'existera pas** ; seuls `EnableBankingProvider` et `MockProvider` implémenteront `BankingProvider`. OFX et Enable Banking partagent uniquement le modèle commun `BankTransaction` et la **base `BankingProviderError`** (définie pour la 1ʳᵉ fois en S12.2, avec une extension propre `EncodingDetectionError`). Le contrat import-linter « `banking.providers` hors `banking.service.polling` » et les erreurs réseau (`ConsentExpiredError`, `RateLimitedError`, …) arrivent avec l'epic Enable Banking, pas en E12. Le corps de l'ADR (décision historique) n'est pas réécrit. Cf. note de réconciliation `docs/roadmap/E12-ofx-import.md`.
