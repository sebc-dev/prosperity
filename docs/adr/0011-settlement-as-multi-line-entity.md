# `Settlement` comme entité multi-line, pas d'état sur `Debt`

> **Refined-by E10 (#23, S10.1).** Trois précisions issues de la matérialisation des modèles `Settlement` / `SettlementLine` :
> 1. **Signe (D-SIGN).** `SettlementLine.amount_cents` est **strictement positif** (CHECK `ck_settlement_lines_amount_positive`), et **non** signé comme l'annonçait ci-dessous le point « `amount_cents` signé / négatif pour les dettes inverses ». Chaque ligne apure une portion d'**une** `Debt` dans le sens propre de cette dette ; le nettage bidirectionnel est porté par l'**orientation intrinsèque de chaque `Debt`** (`from_user_id`/`to_user_id`), pas par un signe sur la ligne. Justification : la formule du solde restant `remaining = debt.amount_cents − SUM(settlement_lines.amount_cents)` et l'invariant « no over-settlement » exigent que les lignes d'une même dette restent dans `[0, amount]` ; un signe casserait les deux.
> 2. **Règle d'égalité au virement.** Corollaire de (1) : la validation server-side ci-dessous (« `sum(SettlementLine.amount_cents)` doit égaler `linked_transaction.amount` ») devient en S10.2 **`Σ amount × signe_direction(debt) == abs(linked_transaction.amount)`** (somme **signée**, `signe = +1` si la dette pointe dans le sens du virement principal, `−1` sinon). L'implémenteur de S10.2 ne doit pas reprendre la formule littérale brute.
> 3. **CASCADE & preuve comptable.** `settlement_lines.debt_id` est `ON DELETE CASCADE` : la suppression d'une `Debt` (ou de sa tx source) efface en cascade ses `SettlementLine`, **y compris pour un règlement non-virtuel** (virement réel). C'est **assumé** : le virement reste tracé par `linked_transaction_id` (`ON DELETE RESTRICT`, jamais effacé silencieusement) ; la distribution par dette est régénérable comme la `Debt` elle-même. Un `Settlement` peut donc subsister sans lignes après un tel CASCADE.

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
