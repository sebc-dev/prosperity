# E08 — Budgets (hiérarchique + alertes)

> **Durée estimée** : 4-5 jours
> **Statut** : not started
> **Dépend de** : E07
> **Bloque** : E11 (debts overflow F10 utilise consommation budget)
> **ADRs activés** : aucun (mécanique conventionnelle, alignée CONTEXT.md)

---

## Objectif

Implémenter F08 partie 2 : `Budget` posé sur une catégorie pour une période + scope (perso/commun) + agrégation hiérarchique (un budget parent agrège les dépenses des enfants). Alertes seuils 80%/100%/120% via le mini-bus `shared/events.py`.

Livrable agrégé : un user crée un budget "Courses, 400€/mois, commun, contributeurs Alice+Bob". Les transactions confirmées de cette catégorie (et descendantes) sont sommées, le pourcentage consommé est calculable, les seuils déclenchent des `BudgetThresholdEvent` que `notifications` (V1) souscrira.

---

## Stories

### S08.1 — Modèle `Budget` + migration

**Livrable observable** : table `budgets` avec FK category + multi-contributeurs.

| Phase | Description | Diff |
|---|---|---|
| **P08.1.1** | Modèles : `Budget` (`id`, `category_id` FK, `period_kind` Literal['monthly','quarterly','yearly'], `period_start` date, `amount_cents`, `scope` Literal['personal','shared'], `created_by`, `archived_at` NULL, `carry_over_remainder` bool default false) + `BudgetContributor` (`budget_id` FK, `user_id` FK) — unique `(budget_id, user_id)`. Note : pour `scope=personal`, un seul contributor (owner) ; pour `scope=shared`, ≥ 2 | ~100 |
| **P08.1.2** | Migration `0011_budgets.py` (`down_revision = "0010"` — la révision `0010_transaction_share_request_id` de S07.4 ; `0010` est déjà pris). Test niveau 1 schema check | ~70 |

---

### S08.2 — Service d'agrégation hiérarchique

**Livrable observable** : `budget.public.compute_consumption(budget_id, as_of=…) → BudgetConsumption(consumed_cents, remaining_cents, percent, splits_count)`.

| Phase | Description | Diff |
|---|---|---|
| **P08.2.1** | `budget/domain.py` : Pydantic `BudgetConsumption`. Fonction pure `compute_period_window(period_kind, period_start, as_of) → (start, end)`. Tests example | ~120 |
| **P08.2.2** | Service `consumption.py` : CTE récursive PostgreSQL pour récupérer toutes les sous-catégories d'une catégorie (utilise `categories` E06). Puis SUM des `splits.amount` confirmés filtré par catégorie ∈ sous-arbre + window de période + contributors (membres du compte commun / owner du compte personnel). Tests intégration avec scénarios variés (catégorie sans enfants, avec enfants, transaction multi-splits dont un seul dans la catégorie...) | ~250 |
| **P08.2.3** | `budget.public.list_active_budgets_for_user(user_id, as_of)` retourne tous les budgets concernés par ce user avec leur consommation actuelle. Tests | ~150 |

---

### S08.3 — Alertes seuils via le mini-bus `shared/events.py`

**Livrable observable** : à chaque write de transaction confirmée, si un budget concerné franchit un seuil (80%/100%/120%), un `BudgetThresholdEvent` est publié.

| Phase | Description | Diff |
|---|---|---|
| **P08.3.1** | Migration `0012_budget_threshold_alerts.py` : table `budget_threshold_alerts (budget_id FK CASCADE, period_start, threshold_pct)` unique. **Server-only** (hors sync rules). Test niveau 1 schema check | ~70 |
| **P08.3.2** | `budget/events.py` : classe `BudgetThresholdEvent(budget_id, threshold_pct, consumed_cents, period_start)` (le mini-bus + `subscribe`/`publish` existent déjà — livrés en S05.4 ; le type concret vit dans le module, **pas** dans `shared/events.py` — contrat #3). `domain.py` : fonction pure `crossed_thresholds(consumed, amount)` (TDD). `budget/service/threshold_detector.py` : handler `on_transaction_confirmed(event)` qui recalcule consumption pour les budgets concernés, tente l'INSERT `ON CONFLICT DO NOTHING` par seuil franchi, publish si nouveau. Câblage `subscribe(TransactionConfirmedEvent, …)` **au composition root** (`backend/main.py`), pas dans `budget/public.py` (cf. Notes : `budget` ⊥ `transactions`). Tests intégration | ~250 |
| **P08.3.3** | Tests scénarios : transaction confirmée qui pousse à 79% → pas d'event ; à 81% → 1 event "80%" ; à 105% → event "100%". Double-confirmation / rejeu idempotent : pas de duplication d'event (idempotence par la table `budget_threshold_alerts`, source de vérité des seuils déjà notifiés) | ~120 |

---

### S08.4 — Routes budgets

**Livrable observable** : CRUD budgets + endpoint consommation.

| Phase | Description | Diff |
|---|---|---|
| **P08.4.1** | Schemas + routes `POST /budgets`, `GET /budgets?as_of=…`, `GET /budgets/{id}`, `PATCH /budgets/{id}` (édition amount, carry_over, scope contributors via sous-routes), `DELETE /budgets/{id}` (archivage). RBAC : un membre voit + édite les budgets shared dont il est contributor + ses budgets personal. Tests | ~250 |
| **P08.4.2** | Route `GET /budgets/{id}/consumption?as_of=…` retourne `BudgetConsumption` détaillée. Tests | ~80 |
| **P08.4.3** | Route `GET /budgets/{id}/contributing-splits?as_of=…` : liste paginée des splits qui contribuent. Utile pour drill-down UI. Tests | ~120 |

---

## Récapitulatif

| ID | Type | Diff | Cumul |
|---|---|---|---|
| S08.1 (2 phases) | Modèles + migration | 170 | 170 |
| S08.2 (3 phases) | Service agrégation hiérarchique | 520 | 690 |
| S08.3 (3 phases) | Alertes seuils (event module + détecteur + idempotence) | 440 | 1130 |
| S08.4 (3 phases) | Routes | 450 | 1580 |
| **Total** | **4 stories / 11 phases** | **~1580 lignes** | |

---

## Critères d'acceptation

- [ ] Un budget posé sur une catégorie parent agrège les splits des sous-catégories
- [ ] La consommation respecte la window de période (`monthly` = mois calendaire courant)
- [ ] Les contributors filtrent : un budget commun ne compte que les splits des comptes communs dont les members sont les contributors
- [ ] Franchissement d'un seuil 80%/100%/120% publie `BudgetThresholdEvent` exactement une fois par période
- [ ] RBAC : un member non-contributor d'un budget commun ne le voit pas
- [ ] Coverage `budget/domain.py` et `budget/service/consumption.py` ≥ 80%

---

## Notes pour l'implémenteur

- 🔒 **`budget` ⊥ `transactions` (modules pairs, même layer).** Le graphe directionnel (`.importlinter` contrat 1, CONTEXT.md §211) place `transactions`, `budget`, `banking` sur le **même** niveau : `budget` **ne peut pas importer** `transactions` (ni `transactions.public`). Conséquences : (1) la consommation lit les tables `transactions`/`splits` via **SQLAlchemy Core / `text()`**, jamais via `transactions.models` (lecture sanctionnée par CONTEXT.md §Splits « agrégation budget » ; seule la *mutation* cross-module est interdite) ; (2) le câblage `subscribe(TransactionConfirmedEvent, …)` vit au **composition root** (`backend/main.py`), `budget.public` n'exposant que le handler `on_transaction_confirmed`. La docstring de `transactions/events.py` annonce ce souscripteur.
- ⚠️ **Le mini-bus `shared/events.py` existe déjà** (livré en S05.4) — on réutilise `subscribe`/`publish`. Les types d'events concrets vivent dans le module publiant (`budget/events.py` pour `BudgetThresholdEvent`), jamais dans `shared` (contrat import-linter #3).
- ⚠️ **Numérotation migrations** : `0010` est pris par S07.4 (`0010_transaction_share_request_id`) → budgets = `0011`, table d'alertes = `0012`.
- La CTE récursive PostgreSQL pour les sous-catégories est performante jusqu'à plusieurs milliers de catégories. Si on observe un ralentissement, on cachera l'arbre côté Python.
- `budget_threshold_alerts` table d'idempotence est server-only (pas dans sync rules). Évite la duplication d'events sur restart serveur.
- `carry_over_remainder` n'est pas implémenté dans le calcul de consumption en E08 — c'est un flag stocké mais ignoré. Implémentation = E11 ou plus tard si besoin observé. Documenter le TODO.
- L'event bus `shared/events.py` est synchrone — pas de async/await dans les subscribers. Pour `notifications` (V1) qui voudra envoyer email/push : le subscriber lance un `BackgroundTasks` FastAPI plutôt que bloquer.
