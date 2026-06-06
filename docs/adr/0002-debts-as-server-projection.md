# Dettes = projection serveur, lecture seule côté client

> **Refined-by E09 (#22, S09.2).** La signature `DebtCalculator : (Transaction, Budget, Account) → list[Debt]` ci-dessous est **affinée** par E09 : pour garder `debts.domain` strictement pur (pas d'import du type `Transaction`, conforme au graphe ADR 0005), le calculator reçoit des **scalaires** — le service dérive `expense_total` (somme des classification legs, ADR 0017) et le passe au domaine. `compute_for_share_request` (sous-cas `personal_share_request`) est la méthode MVP ; `compute_for_overflow` (sous-cas `shared_account_overflow`, F10) est livrée en E11 (S11.2) — elle reçoit elle aussi des **scalaires** (`budget_remaining_before: Money | None` dérivé du budget par le service S11.3), JAMAIS l'argument `Budget` lui-même, conforme à l'esprit du présent encart. La matérialisation E09 se fait dans `create_share_request` (acte explicite REST) sur une tx **`confirmed`** (montant gelé, ADR 0001) ; la matérialisation « à chaque write de transaction » via le write upload handler (ADR 0014) reste la voie du sous-cas overflow (E11).

Les dettes sont mécaniquement dérivées des transactions, des budgets, des quote-parts et des overrides, et leur génération est sensible à l'ordre d'arrivée des écritures (notamment pour la mécanique d'excédent budgétaire F10). Permettre l'édition concurrente d'une `Debt` côté client introduirait des conflits sans solution simple sous PowerSync. Nous décidons que la table `debts` est une **projection serveur** matérialisée à chaque write de transaction par le module `debts`, et exposée **en lecture seule côté client** via les sync rules PowerSync. Les seuls leviers d'écriture utilisateur sont `share_ratio` (endpoint dédié, scalaire LWW-safe), `debt_generation_override` (sur la transaction source), et la création d'un `settlement` (transaction normale).

## Consequences

- Le `domain.py` du module `debts` expose un `DebtCalculator` pur — fonction de `(Transaction, Budget, Account) → list[Debt]` — pas un `DebtRepository` éditable.
- Le `service.py` matérialise les dettes via SQLAlchemy après chaque write de transaction (idempotent : recalcul complet du sous-ensemble de dettes concernées par la transaction touchée).
- La séparation est nette : *intentions utilisateur* écrites côté client (transaction, quote-part, override) ; *dérivés* calculés côté serveur (dettes, projections, agrégations).
- L'écran "mes dettes" reste réactif offline parce que la table `debts` est sync en lecture sur le device.
- Décision dépendante de l'ADR 0001 (aggregate immutable).
