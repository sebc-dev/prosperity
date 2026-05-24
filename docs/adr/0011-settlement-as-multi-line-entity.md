# `Settlement` comme entité multi-line, pas d'état sur `Debt`

F09 demande à la fois (i) trois cas réels distincts pour un règlement (virement intra-foyer entre deux comptes du foyer, virement externe vers contrepartie non modélisée, compensation virtuelle sans mouvement d'argent), (ii) le nettage de plusieurs dettes en un seul règlement (y compris cross-direction Bob→Alice et Alice→Bob), et (iii) la compatibilité avec l'aggregate immutable (ADR 0001) et la projection read-only des dettes (ADR 0002). Nous décidons d'introduire **`Settlement` et `SettlementLine` comme entités dédiées** :

- `Settlement` porte un `type` (`internal_transfer` / `external_transfer` / `virtual`), un `linked_transaction_id` optionnel (NULL pour `virtual`, FK vers la `Transaction` de virement préalable pour les deux autres types), une `settled_at`, un auteur, et une note.
- `SettlementLine` distribue le montant apuré sur les dettes individuelles (`amount_cents` signé pour permettre le nettage bidirectionnel : positif pour la dette principale, négatif pour les dettes inverses entrant dans le netting).

**Pas d'état sur `Debt`** : le solde restant se calcule par `debt.amount_cents - sum(settlement_lines.amount_cents)`. Une dette est "réglée" quand le solde tombe à 0, "partielle" entre les deux. Cette approche conserve la projection read-only de `Debt` et permet les partial settlements sans state machine.

## Consequences

- Le virement (internal/external) doit exister **comme `Transaction` normale d'abord**, le `Settlement` y est lié ensuite. Cohérent avec ADR 0001 (transaction = aggregate immutable, première classe).
- Validation server-side : `sum(SettlementLine.amount_cents)` doit égaler `linked_transaction.amount` pour les types non-virtuels.
- Tous les `debt_id` référencés par un même `Settlement` doivent concerner les **deux mêmes contreparties** ; rejeté sinon (un règlement = un seul couple de contreparties).
- Hypothesis property naturelle : *conservation du solde net entre deux contreparties* — `sum(debts entre A et B) - sum(settlement_lines entre A et B) == 0` après apurement complet.
- Suggestion automatique des dettes à netter (UI) repoussée en V2.
- Décision dépendante des ADR 0001 et 0002.
