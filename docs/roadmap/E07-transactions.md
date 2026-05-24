# E07 — Transactions module (aggregate immutable)

> **Durée estimée** : 7-10 jours
> **Statut** : not started
> **Dépend de** : E05, E06
> **Bloque** : E08, E09, E11, E12, E13
> **ADRs activés** : 0001 (aggregate immutable), 0008 (Money value object utilisé)

---

## Objectif

Implémenter F05 dans toute sa rigueur : `Transaction` aggregate root immutable à `confirmed`, splits relationnels avec FK CASCADE, value object `Money`, state machine `draft → planned → confirmed → void`, validation zero-sum, set explicite de champs éditables après confirmation. C'est **l'archétype** des modules à `domain.py` : le pattern développé ici sera reproduit pour `reconciliation`, `debts`, `forecasting`, `mcp`.

Livrable agrégé : un user peut créer une transaction draft, la confirmer (transition irréversible vers immutabilité partielle), la void (état terminal). Édition libre en draft, restreinte en confirmed (catégorie, tags, description, debt_generation_override, share_request seulement).

---

## Stories

### S07.1 — `Money` value object (shared)

**Livrable observable** : `Money(100, "EUR") + Money(50, "EUR") == Money(150, "EUR")` ; `Money(100, "EUR") + Money(50, "USD")` raise `IncompatibleCurrencyError`.

| Phase | Description | Diff |
|---|---|---|
| **P07.1.1** | `shared/currency.py` : type `Currency` Literal des ISO 4217 utilisés (EUR, USD, GBP, CHF — extensible). Validateur Pydantic | ~80 |
| **P07.1.2** | `shared/money.py` : Pydantic `Money(amount_cents: int, currency: Currency)`, opérateurs `__add__`, `__sub__`, `__mul__` (× scalaire), `__neg__`, `__eq__`, `__lt__`. `IncompatibleCurrencyError` exception. Tests example + property Hypothesis : commutativité, associativité, absence de mélange devises | ~200 |
| **P07.1.3** | `shared/money.py` formatters : `format_french()` retourne "1 234,56 €", parser inverse. Tests | ~100 |

---

### S07.2 — Modèles `Transaction` + `Split`

**Livrable observable** : tables `transactions` + `splits` créées avec FK CASCADE, factory produit transaction zero-sum.

| Phase | Description | Diff |
|---|---|---|
| **P07.2.1** | Modèle `Transaction` dans `modules/transactions/models.py` : `id` UUID, `account_id` FK (denormalisé pour bucket PowerSync), `date`, `state` (Literal), `payee`, `description`, `category_id` FK NULL (catégorie "principale" — peut être NULL si transfert), `created_by` FK, `created_at`, `confirmed_at` NULL, `voided_at` NULL, `tags` text[], `debt_generation_override` Literal default 'default'. PAS de champs `amount` ou `bank_transaction_id` (l'amount est dérivé des splits, le lien bank vit dans Reconciliation à E13/V1) | ~120 |
| **P07.2.2** | Modèle `Split` : `id`, `transaction_id` FK CASCADE, `account_id` FK, `category_id` FK NULL, `amount_cents` bigint, `currency` text, `savings_goal_id` FK NULL (préparation E12 banking, ou même plus tard pour savings). Indexes `(transaction_id)`, `(account_id)`, `(category_id)` | ~100 |
| **P07.2.3** | Migration `0009_transactions_and_splits.py`. Test niveau 1 schema check. Test : suppression d'une transaction CASCADE les splits | ~120 |
| **P07.2.4** | `tests/factories/sqlalchemy.py` : `TransactionFactory` + `SplitFactory` qui génèrent une transaction zero-sum par défaut (un split débit + un split crédit équilibrés). Tests | ~100 |

---

### S07.3 — Domain.py : aggregate immutable + state machine

**Livrable observable** : `Transaction` Pydantic du domain refuse les transitions invalides, refuse l'édition d'un champ gelé sur `confirmed`.

| Phase | Description | Diff |
|---|---|---|
| **P07.3.1** | `modules/transactions/domain.py` : Pydantic `Transaction(BaseModel)` avec `splits: list[Split]`. Validators : `sum(splits.amount) == 0` enforced si état `confirmed`. State enum + transitions autorisées en const `STATE_TRANSITIONS`. Tests example | ~150 |
| **P07.3.2** | `TransactionImmutabilityChecker` : pour une `Transaction` en `confirmed`, refuse toute mutation hors du set `{category_id, tags, description, debt_generation_override, share_request_added, share_request_removed}`. Helper `check_mutation_allowed(old, new) → raises ImmutableFieldViolation`. Tests Hypothesis : pour toute paire (old, new) qui ne diffère que sur les champs allowed, accepte ; sinon refuse | ~200 |
| **P07.3.3** | `TransactionStateMachine` : valid transitions `draft → planned → confirmed`, `* → void` (sauf `void → *` interdit), `confirmed → planned` INTERDIT (cf. ADR 0001 / Q8 reconciliation). Tests | ~120 |
| **P07.3.4** | `UncategorizedExpenseError` : `confirm()` refuse si un split dépense (non-transfert) a `category_id IS NULL`. Helper `is_transfer(split) → bool` (vrai si compte source ET compte cible sont des comptes du foyer). Tests | ~120 |

---

### S07.4 — Service transactions

**Livrable observable** : `transactions.public.create_draft`, `add_split`, `transition_to_planned`, `transition_to_confirmed`, `update_editable_fields`, `void` fonctionnent et émettent les bons events.

| Phase | Description | Diff |
|---|---|---|
| **P07.4.1** | `modules/transactions/service/lifecycle.py` : `create_draft(account_id, by_user_id) → Transaction`, `add_split(tx_id, ...)`, `remove_split(tx_id, split_id)`. Validation Pydantic + persistance SQLA en transaction. Tests intégration | ~200 |
| **P07.4.2** | Transitions : `transition_to_planned(tx_id)` (vérifie zero-sum), `transition_to_confirmed(tx_id)` (vérifie zero-sum + tous splits dépenses ont catégorie), `void(tx_id, reason)`. Emit `TransactionConfirmedEvent`, `TransactionVoidedEvent` via `shared/events.py`. Tests | ~250 |
| **P07.4.3** | `update_editable_fields(tx_id, **fields)` : vérifie via `TransactionImmutabilityChecker`, applique, persiste. Tests : essayer d'éditer `amount_cents` d'un split d'une `confirmed` → `ImmutableFieldViolation` ; éditer `category_id` → OK | ~180 |
| **P07.4.4** | `transactions.public.py` : ré-exporte `create_draft`, `transition_to_*`, `update_editable_fields`, `void`, `TransactionConfirmedEvent`, etc. Import-linter passe | ~50 |

---

### S07.5 — Routes HTTP transactions

**Livrable observable** : CRUD complet via HTTP avec auth + RBAC (membre du compte concerné).

| Phase | Description | Diff |
|---|---|---|
| **P07.5.1** | Schemas Pydantic API (séparés du domain) : `TransactionCreate`, `SplitInput`, `TransactionResponse`. Route `POST /accounts/{id}/transactions` (crée draft + ajoute splits dans le payload). Tests httpx avec RBAC (user non-membre du compte → 403) | ~200 |
| **P07.5.2** | Routes transitions : `POST /transactions/{id}/confirm`, `POST /transactions/{id}/void`, `POST /transactions/{id}/plan`. Tests | ~150 |
| **P07.5.3** | Route `PATCH /transactions/{id}` : seuls les champs allowed (category, tags, description, debt_generation_override) acceptés ; sinon 422 typé. Tests | ~150 |
| **P07.5.4** | Route `GET /transactions?account_id=…&from=…&to=…&state=…` avec pagination cursor-based. Filtres conformes RBAC. Tests | ~180 |

---

### S07.6 — Hypothesis : invariants aggregate

**Livrable observable** : property tests passent sur les invariants critiques.

| Phase | Description | Diff |
|---|---|---|
| **P07.6.1** | `tests/strategies.py` : `money_strategy`, `balanced_splits_strategy(n_splits=…)`, `transaction_draft_strategy`, `transaction_confirmed_strategy` | ~180 |
| **P07.6.2** | Properties : (1) `confirmed → confirmed` après `update_editable_fields` allowed = sum splits inchangée ; (2) `void` ne change pas les splits ; (3) toute transition non listée dans `STATE_TRANSITIONS` raise ; (4) deux confirms en parallèle (idempotence) = même état | ~150 |

---

## Récapitulatif

| ID | Type | Diff | Cumul |
|---|---|---|---|
| S07.1 (3 phases) | Money/Currency shared | 380 | 380 |
| S07.2 (4 phases) | Modèles + migration + factories | 440 | 820 |
| S07.3 (4 phases) | Domain immutable + state machine | 590 | 1410 |
| S07.4 (4 phases) | Service lifecycle | 680 | 2090 |
| S07.5 (4 phases) | Routes | 680 | 2770 |
| S07.6 (2 phases) | Hypothesis | 330 | 3100 |
| **Total** | **6 stories / 21 phases** | **~3100 lignes** | |

---

## Critères d'acceptation

- [ ] `Money + Money` cross-devise raise `IncompatibleCurrencyError`
- [ ] Transaction `confirmed` ne peut pas avoir `sum(splits.amount) ≠ 0`
- [ ] Transition `confirmed → planned` interdite (raise)
- [ ] Édition d'un champ non-allowed sur `confirmed` raise `ImmutableFieldViolation`
- [ ] Confirmer une transaction avec split dépense sans catégorie raise `UncategorizedExpenseError`
- [ ] Routes RBAC : un user non-membre du compte ne peut ni créer, ni lire, ni éditer
- [ ] DomainEvent `TransactionConfirmedEvent` publié sur le bus
- [ ] Property Hypothesis : 4 invariants documentés passent avec `max_examples=200`
- [ ] Coverage `transactions/domain.py` ≥ 90%, service ≥ 75%

---

## Notes pour l'implémenteur

- **C'est l'archétype.** Ce module sert de patron pour les 4 autres modules à `domain.py`. Soigne la structure : `domain.py` pur (Pydantic + fonctions), `service/` (sous-dossier avec lifecycle.py, queries.py si besoin), `models.py` SQLA, `schemas.py` API, `transports/http.py`. Ce découpage sera répliqué.
- **Domain Pydantic vs SQLA model** : deux modèles séparés. Le domain `Transaction` est pur (sans session DB) ; le service fait le mapping SQLA ↔ domain. Coût : un mapper. Bénéfice : tests domain ultra-rapides.
- **Pas de `bank_transaction_id` sur transaction** : c'est `Reconciliation` (E13/V1) qui porte le lien. Ne pas anticiper en mettant un champ dormant.
- **`share_request` ajout/retrait** = champ allowed après `confirmed` mais l'entité `ShareRequest` elle-même vit dans le module `debts` (E09). Le `Transaction.share_request_id NULL` est mutable après confirmed (set/unset). Le check Pydantic doit le savoir.
- **`debt_generation_override`** = Literal['default', 'force_full_debt', 'force_no_debt']. Default au create = 'default'. Modifiable après `confirmed` (cf. ADR 0011/Q2).
- **Property Hypothesis idempotence** : un test important parce qu'il anticipe l'arrivée du write upload handler (E13) qui rejouera des mutations. Mieux vaut découvrir ici qu'à l'intégration sync.
