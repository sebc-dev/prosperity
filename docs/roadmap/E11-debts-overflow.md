# E11 — Debts overflow F10

> **Durée estimée** : 3-4 jours
> **Statut** : not started
> **Dépend de** : E08, E10
> **Bloque** : E13 (write upload handler matérialise les dettes overflow synchronement)
> **ADRs activés** : 0002 (étendu pour overflow), 0011 (réutilisé via `compute_remaining`)

---

## Objectif

Implémenter F10 : mécanique d'excédent budgétaire sur compte commun. À chaque transaction confirmée sur un compte commun avec catégorie liée à un budget actif, calculer `E = max(0, M - R)` (excédent) et matérialiser une (ou plusieurs) `Debt` d'origine `shared_account_overflow` selon la quote-part du compte. Honorer `debt_generation_override` (`default` / `force_full_debt` / `force_no_debt`).

Livrable agrégé : Alice paie 100€ Courses depuis le compte commun 50/50 alors que le budget Courses a 50€ restants → 50€ d'excédent matérialise 25€ de dette Bob → Alice. Si Alice marque la transaction `force_full_debt`, 100€ entiers matérialisent 50€ de dette Bob → Alice.

---

## Stories

### S11.1 — Champ `debt_generation_override` sur `Transaction`

**Livrable observable** : champ déjà créé en E07 (anticipé). Migration éventuelle si on n'a pas anticipé.

| Phase | Description | Diff |
|---|---|---|
| **P11.1.1** | Vérifier que le champ `debt_generation_override` Literal['default','force_full_debt','force_no_debt'] a bien été ajouté en E07. Si non, migration `0013_add_debt_generation_override.py` + update modèle. Tests | ~70 |
| **P11.1.2** | Étendre `transactions.public.update_editable_fields` pour accepter `debt_generation_override` même après `confirmed` (déjà dans le set allowed). Tests : modification après confirmed acceptée, autres champs gelés toujours refusés | ~80 |

---

### S11.2 — `DebtCalculator.compute_overflow` (domain pur)

**Livrable observable** : fonction pure qui prend une `Transaction`, son compte commun, le budget concerné, la consommation pré-transaction → retourne la liste de `Debt` à matérialiser.

| Phase | Description | Diff |
|---|---|---|
| **P11.2.1** | `debts/domain.py` étend : `compute_overflow(tx, account_with_members, budget_consumption_before, override) → list[Debt]`. Logique : si `override == 'force_no_debt'` → []. Si `override == 'force_full_debt'` → dette répartie selon `default_share_ratio` sur l'amount total. Sinon : calcule `E = max(0, tx.amount - budget.remaining_before)` ; si E > 0, dette répartie selon ratios sur E. Tests example pour tous les cas du tableau F10 | ~200 |
| **P11.2.2** | Property Hypothesis : (1) somme des dettes générées == `E × (1 - share du créateur)` car le créateur n'a pas de dette envers lui-même, (2) cas `default` + budget largement restant → [] vide, (3) cas `force_full_debt` + transaction sans budget → idem que cas overflow sur transaction non-budgétisée. Tests | ~180 |

---

### S11.3 — Service de matérialisation overflow

**Livrable observable** : à chaque `TransactionConfirmedEvent` sur compte commun, `debts.service` re-calcule et persiste les dettes overflow. Idempotent.

| Phase | Description | Diff |
|---|---|---|
| **P11.3.1** | `debts/service/overflow_materializer.py` : souscrit à `TransactionConfirmedEvent`. Pour transaction sur compte commun : (1) cherche budget actif sur la catégorie, (2) calcule consumption avant transaction (window de période), (3) call `compute_overflow`, (4) insert/replace les `Debt` d'origine `shared_account_overflow` pour cette `source_transaction_id`. **Idempotent** : `INSERT ... ON CONFLICT (source_transaction_id, from_user_id, to_user_id, origin) DO UPDATE SET amount_cents = ...`. Tests intégration | ~280 |
| **P11.3.2** | Souscrire aussi à `TransactionVoidedEvent` : supprime les `Debt` d'origine `shared_account_overflow` pour cette tx. Tests | ~80 |
| **P11.3.3** | Souscrire à `debt_generation_override` change (nouveau `TransactionEditableFieldsChangedEvent` à ajouter dans `transactions.public` events) : re-matérialise. Tests | ~120 |

---

### S11.4 — Reclassement F10 : modif de budget après coup

**Livrable observable** : ajouter un budget après-coup couvrant une transaction passée doit re-matérialiser les dettes générées (recalcul, pas suppression hard d'historique).

| Phase | Description | Diff |
|---|---|---|
| **P11.4.1** | Souscrire à `BudgetCreatedEvent` et `BudgetUpdatedEvent` (à ajouter dans `budget.public` events) : pour toutes les transactions confirmées de la catégorie dans la période du budget, re-matérialiser overflow. Idempotent. Tests intégration : créer transaction sans budget → dette générée ; ajouter budget couvrant → dette retirée | ~200 |
| **P11.4.2** | Audit log : laisser une trace `debts_recomputed_on_budget_event` (timestamp, budget_id, transactions_recomputed_count). Tests | ~80 |

---

### S11.5 — Hypothesis : invariants overflow

| Phase | Description | Diff |
|---|---|---|
| **P11.5.1** | Strategies : `account_with_members_strategy`, `budget_strategy`, `confirmed_tx_on_shared_account_strategy`. Property : (1) pour tout scénario (compte, budget, transactions), recalculer 2x = même set de dettes (idempotence ADR 0002) ; (2) `force_no_debt` n'a jamais d'effet sur les dettes ; (3) `force_full_debt` génère toujours `sum(debts) == tx.amount × (1 - creator_share)` | ~200 |

---

## Récapitulatif

| ID | Type | Diff | Cumul |
|---|---|---|---|
| S11.1 (2 phases) | debt_generation_override field | 150 | 150 |
| S11.2 (2 phases) | compute_overflow domain | 380 | 530 |
| S11.3 (3 phases) | Service matérialisation | 480 | 1010 |
| S11.4 (2 phases) | Reclassement budget | 280 | 1290 |
| S11.5 (1 phase) | Hypothesis | 200 | 1490 |
| **Total** | **5 stories / 10 phases** | **~1490 lignes** | |

---

## Critères d'acceptation

- [ ] Transaction `default` sur compte commun avec budget non dépassé → aucune `Debt` overflow
- [ ] Transaction `default` qui dépasse → dette = excédent E × quote-part autres members
- [ ] Transaction `force_full_debt` → dette = montant total × quote-part autres members (+ exclusion du compteur budget E08)
- [ ] Transaction `force_no_debt` → aucune dette, même si dépassement
- [ ] Re-matérialisation idempotente : recalculer 2x = même état
- [ ] Void d'une transaction supprime ses dettes overflow
- [ ] Ajout d'un budget couvrant des transactions passées re-matérialise (recalcul, pas perte d'historique car les `share_request` ne sont pas touchés)
- [ ] Property Hypothesis : 3 invariants documentés passent

---

## Notes pour l'implémenteur

- Le `force_full_debt` exclut la transaction du compteur de consommation budget : à propager dans `budget/service/consumption.py` (filtrer `WHERE debt_generation_override != 'force_full_debt'` dans la requête de consumption). C'est un changement à E08 ; en E11 on documente le TODO et on patche E08 dans une PR liée.
- L'unique key pour idempotence ON CONFLICT : `(source_transaction_id, from_user_id, to_user_id, origin)`. À ajouter en migration partielle (`UNIQUE WHERE origin = 'shared_account_overflow'`).
- Les dettes `personal_share_request` ne sont **jamais** touchées par la mécanique overflow (l'origine est exclusive). Bien filtrer.
- Le re-calc déclenché par `BudgetCreatedEvent` peut être coûteux si beaucoup de transactions passées. En E11 : pas d'optim, juste un compteur d'audit. Si on observe un ralentissement réel en usage, on découpera en batch async (V1.5).
