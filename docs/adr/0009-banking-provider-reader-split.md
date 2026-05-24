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
