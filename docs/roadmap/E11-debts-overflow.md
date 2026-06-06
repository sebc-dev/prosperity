# E11 — Debts overflow F10

> **Durée estimée** : 3-4 jours
> **Statut** : not started
> **Dépend de** : E08.5, E10
> **Bloque** : E13 (write upload handler matérialise les dettes overflow synchronement)
> **ADRs activés** : 0002 (étendu pour overflow), 0011 (réutilisé via `compute_remaining`), 0017 (prérequis : levé par E08.5)
>
> ⚠️ **Prérequis dur E08.5 (ADR 0017).** Le livrable ci-dessous suppose qu'une transaction **confirmée** consomme un budget (P11.3.2 : « restant **avant** tx »). Tant que la contradiction E07/E08 n'est pas levée par E08.5 (`leg_role` sur `Split`), aucune transaction confirmable ne consomme — l'overflow serait toujours nul. Voir [#133](https://github.com/sebc-dev/prosperity/issues/133).

---

## Objectif

Implémenter F10 : mécanique d'excédent budgétaire sur compte commun. À chaque transaction confirmée sur un compte commun avec catégorie liée à un budget actif, calculer `E = max(0, M - R)` (excédent) et matérialiser une (ou plusieurs) `Debt` d'origine `shared_account_overflow` selon la quote-part du compte. Honorer `debt_generation_override` (`default` / `force_full_debt` / `force_no_debt`).

Livrable agrégé : Alice paie 100€ Courses depuis le compte commun 50/50 alors que le budget Courses a 50€ restants → 50€ d'excédent matérialise 25€ de dette Bob → Alice. Si Alice marque la transaction `force_full_debt`, 100€ entiers matérialisent 50€ de dette Bob → Alice.

---

## Stories

> **Issues GitHub** : #164 (S11.1) · #165 (S11.2) · #166 (S11.3) · #167 (S11.4) · #168 (S11.5).
> **Deltas réconciliés au moment du découpage en issues** : (D1) le champ `debt_generation_override` + son éditabilité post-`confirmed` sont **déjà livrés en E07** (colonne en migration `0009`, CHECK `ck_transactions_debt_generation_override` en `0010`, `EDITABLE_AFTER_CONFIRMED`, issue #114) → S11.1 ne crée rien, elle **verrouille** le socle et ajoute l'event d'édition ; (D2) l'exclusion E08 de `force_full_debt` du compteur de consommation est **déjà implémentée** (`budget/service/consumption.py`) → la note implémenteur §1 ci-dessous est **caduque** ; (D4) la migration de l'index unique d'idempotence devient une **phase dédiée** (P11.3.1) ; (D5) la méthode domaine s'appelle **`compute_for_overflow`** (nom déjà réservé par la docstring du `DebtCalculator`) ; (D7) `BudgetCreatedEvent`/`BudgetUpdatedEvent` n'existent pas encore → S11.4 les ajoute côté `budget`.

### S11.1 — Socle `debt_generation_override` : verrou + event d'édition

**Livrable observable** : le socle (champ + éditabilité post-`confirmed` + exclusion E08) est **déjà livré (E07/E08)** ; cette story le **verrouille par test de régression** et ajoute le seul manquant, l'event `TransactionEditableFieldsChangedEvent`.

| Phase | Description | Diff |
|---|---|---|
| **P11.1.1** | Verrou de régression (tests only) : `debt_generation_override ∈ EDITABLE_AFTER_CONFIRMED`, modification post-`confirmed` acceptée / champs financiers gelés, transaction `force_full_debt` exclue de `compute_consumption`. Aucune migration (colonne déjà en `0009`, CHECK en `0010`) | ~70 |
| **P11.1.2** | Ajouter `TransactionEditableFieldsChangedEvent` (`transactions/events.py`, `{transaction_id, changed_fields}`), l'émettre depuis `update_editable_fields`, le ré-exporter dans `transactions.public`. Tests : spy reçoit l'event au changement d'override, non émis si rien ne change | ~90 |

---

### S11.2 — `DebtCalculator.compute_for_overflow` (domain pur)

**Livrable observable** : fonction **pure scalaire** (gabarit `compute_for_share_request`) qui prend des valeurs (montant dépense, restant budget pré-transaction, membres + quotes-parts, override) — **jamais** un `Transaction` ni une `Session` — et retourne la liste de `Debt` à matérialiser.

| Phase | Description | Diff |
|---|---|---|
| **P11.2.1** | `debts/domain.py` étend : `compute_for_overflow(*, expense_total, budget_remaining_before, account_members, payer_user_id, override, …) → list[Debt]`. Scalaires uniquement (pas de `Transaction`). Logique : `force_no_debt` → [] ; base = total (`force_full_debt`) ou `max(0, total − restant)` (`default`) ; répartition sur les membres ≠ payeur selon `share_ratio` ; gardes famille `DebtCalculationError`. Tests example tous cas F10 | ~210 |
| **P11.2.2** | Property Hypothesis : (1) somme des dettes générées == `E × (1 - share du créateur)` car le créateur n'a pas de dette envers lui-même, (2) cas `default` + budget largement restant → [] vide, (3) cas `force_full_debt` + transaction sans budget → idem que cas overflow sur transaction non-budgétisée. Tests | ~180 |

---

### S11.3 — Service de matérialisation overflow

**Livrable observable** : à chaque `TransactionConfirmedEvent` sur compte commun, `debts.service` re-calcule et persiste les dettes overflow. Idempotent.

| Phase | Description | Diff |
|---|---|---|
| **P11.3.1** | **Migration dédiée** (`docs/roadmap/README.md` §Règles d'atomicité, règle 5) : index UNIQUE partiel `(source_transaction_id, from_user_id, to_user_id, origin) WHERE origin = 'shared_account_overflow'` sur `debts` + déclaration ORM (parité create_all/Alembic, gabarit `uq_share_requests_active`). Test schema Niveau 1 | ~80 |
| **P11.3.2** | `debts/service/overflow_materializer.py` : handler async `TransactionConfirmedEvent`. Tx compte commun : (1) budget **le plus spécifique** sur la catégorie (cf. `CONTEXT.md` §Excédent), (2) restant **avant** tx = `budget − consommation des tx (date, id) < (date_tx, id_tx)` (**fenêtre ordonnée**, conservation `Σ E = max(0, ΣM − budget)` ; param `before` optionnel sur `budget.public.compute_consumption`), (3) membres + quotes-parts (`accounts.public`), (4) `compute_for_overflow`, (5) **upsert** `ON CONFLICT … DO UPDATE` + DELETE complémentaire des lignes overflow caduques. Câblage `subscribe_async` au composition root. **Nouvel arc `debts → budget.public` → `ignore_imports` du contrat `2-debts`**. Tests intégration **+ property Hypothesis de conservation/idempotence anticipée** (le reste des properties reste en S11.5) | ~300 |
| **P11.3.3** | Souscrire `TransactionVoidedEvent` : supprime les `Debt` `shared_account_overflow` de la tx (filtre origine — `personal_share_request` intactes). Tests | ~80 |
| **P11.3.4** | Souscrire `TransactionEditableFieldsChangedEvent` (S11.1) : re-matérialise si `debt_generation_override` a changé (réutilise P11.3.2). Tests | ~120 |

---

### S11.4 — Reclassement F10 : modif de budget après coup

**Livrable observable** : ajouter un budget après-coup couvrant une transaction passée doit re-matérialiser les dettes générées (recalcul, pas suppression hard d'historique).

| Phase | Description | Diff |
|---|---|---|
| **P11.4.1** | Souscrire à `BudgetCreatedEvent` et `BudgetUpdatedEvent` (à ajouter dans `budget.public` events) : pour toutes les transactions confirmées de la catégorie dans la période du budget, re-matérialiser overflow. Idempotent. Tests intégration : créer transaction sans budget → dette générée ; ajouter budget couvrant → dette retirée | ~200 |
| **P11.4.2** | Audit log : laisser une trace `debts_recomputed_on_budget_event` (timestamp, budget_id, transactions_recomputed_count). Tests | ~80 |
| **P11.4.3** | **Re-matérialisation sur édition `category_id`** (delta reporté de S11.3) : `rematerialize_overflow_on_edit` ne réagit en S11.3 qu'à `debt_generation_override` ; étendre à `category_id` (overflow-relevant : sélectionne le budget couvrant, donc le restant, donc la base) et re-matérialiser les **voisines de période** dont le restant est décalé (cf. `CONTEXT.md` §Excédent _Limite V1_). Tests : éditer la catégorie d'une tx confirmée → overflow recalculé sur le nouveau budget couvrant ; voisines re-matérialisées | ~120 |

---

### S11.5 — Hypothesis : invariants overflow

| Phase | Description | Diff |
|---|---|---|
| **P11.5.1** | Strategies : `account_with_members_strategy`, `budget_strategy`, `confirmed_tx_on_shared_account_strategy`. Property : (1) pour tout scénario (compte, budget, transactions), recalculer 2x = même set de dettes (idempotence ADR 0002) ; (2) `force_no_debt` n'a jamais d'effet sur les dettes ; (3) `force_full_debt` génère toujours `sum(debts) == tx.amount × (1 - creator_share)` | ~200 |

---

## Récapitulatif

| ID | Type | Diff | Cumul |
|---|---|---|---|
| S11.1 (2 phases) | Socle override : verrou + event d'édition | 160 | 160 |
| S11.2 (2 phases) | `compute_for_overflow` domain | 390 | 550 |
| S11.3 (4 phases) | Service matérialisation (+ migration dédiée) | 560 | 1110 |
| S11.4 (2 phases) | Reclassement budget | 280 | 1390 |
| S11.5 (1 phase) | Hypothesis | 200 | 1590 |
| **Total** | **5 stories / 11 phases** | **~1590 lignes** | |

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

- ~~Le `force_full_debt` exclut la transaction du compteur de consommation budget : à propager dans `budget/service/consumption.py`…~~ **CADUC (D2)** : l'exclusion `WHERE debt_generation_override != 'force_full_debt'` est **déjà implémentée** dans `budget/service/consumption.py` (`_consumption_filters`, source unique agrégat + drill-down). S11.1 ne fait que la **verrouiller** par test de régression.
- L'unique key pour idempotence ON CONFLICT : `(source_transaction_id, from_user_id, to_user_id, origin)`. À ajouter en migration partielle (`UNIQUE WHERE origin = 'shared_account_overflow'`).
- Les dettes `personal_share_request` ne sont **jamais** touchées par la mécanique overflow (l'origine est exclusive). Bien filtrer.
- **`default` sans budget actif → dette sur le montant entier** (`base = M`, équivalent `force_full_debt`). Tranché produit le 2026-06-06 : l'alternative « sans budget ⇒ no-op / aucune dette » (formulation initiale du corps d'issue, cf. ⚠️ ci-dessous) est **écartée** au profit de « base = montant entier ». Cohérent avec : le domaine S11.2 mergé (`compute_for_overflow` : `budget_remaining_before is None → base = expense_total`), la property P11.2.2 (3) (`force_full_debt` ≡ overflow d'une dépense non budgétée), et le reclassement S11.4 (« créer transaction sans budget → dette générée ; ajouter budget couvrant → dette retirée »). ⚠️ La formulation « sans budget ⇒ no-op » / le test « budget absent ignoré » du **corps de l'issue #166** sont **caducs** — le materializer appelle toujours `compute_for_overflow` (avec `budget_remaining_before=None` si aucun budget) ; seuls une tx **non commune** ou un override `force_no_debt` ne génèrent rien. Voir le plan posté en commentaire sur #166.
- Le re-calc déclenché par `BudgetCreatedEvent` peut être coûteux si beaucoup de transactions passées. En E11 : pas d'optim, juste un compteur d'audit. Si on observe un ralentissement réel en usage, on découpera en batch async (V1.5).
