# Phase 6: Envelope Budgets - Context

**Gathered:** 2026-04-22
**Status:** Ready for planning

<domain>
## Phase Boundary

Les utilisateurs peuvent budgétiser via des enveloppes **par compte bancaire**, avec suivi automatique des dépenses imputées depuis les transactions catégorisées. Cette phase couvre : CRUD d'enveloppes, liaison à une ou plusieurs catégories, allocation mensuelle (budget fixe + overrides), rollover configurable, indicateurs visuels de dépassement, et historique de consommation. Les enveloppes transversales (cross-account) restent hors scope (PROJECT.md Key Decision). Le dashboard consolidé multi-comptes relève de la Phase 10.

</domain>

<decisions>
## Implementation Decisions

### Liaison enveloppe ↔ catégories (ENVL-03)
- **D-01:** Relation **N:N** via nouvelle table de jonction `envelope_categories (envelope_id FK, category_id FK, PRIMARY KEY composite)`. Une enveloppe peut agréger plusieurs catégories (ex: « Vie quotidienne » = Alimentation + Transport). Contrainte métier : **une catégorie ne peut être liée qu'à UNE enveloppe par compte** (empêche la double-imputation). Validation au service (pas via contrainte SQL composite sur envelope_id/bank_account_id/category_id pour garder la table simple).
- **D-02:** Lier une **catégorie racine** embrasse automatiquement ses **sous-catégories**. Le calcul du consumed traite la hiérarchie via une recursive CTE ou `IN (parent_id, children_ids)` résolu côté service. Cohérent avec la taxonomie 2-niveaux établie en Phase 4.
- **D-03:** Les **splits de transaction** (TXNS-06) sont imputés **au prorata** : chaque ligne de `transaction_splits` impute l'enveloppe liée à la catégorie de ce split pour son montant partiel. Le SUM du consumed doit scanner `transactions.category_id` ET `transaction_splits` (UNION ou JOIN avec CASE).
- **D-04:** Une transaction dont la catégorie n'est liée à **aucune enveloppe** est **ignorée silencieusement** — elle reste dans `transactions` mais n'apparaît dans aucun solde d'enveloppe. Pas de compteur « hors budget » en v1.

### Visibilité et portée sur compte partagé (blocker STATE.md)
- **D-05:** Sur un compte **SHARED** (Account.accountType=SHARED), toutes les enveloppes sont `scope=SHARED, owner=null`. User A et User B (ayant accès au compte) voient et modifient **les mêmes enveloppes** — un compte commun ⇒ un budget commun. Un seul set d'enveloppes par compte commun.
- **D-06:** Sur un compte **PERSONAL** (Account.accountType=PERSONAL), les enveloppes sont `scope=PERSONAL, owner=user_du_compte`. Visibilité = règles existantes `AccountAccessRepository` (typiquement l'owner seul, sauf partage explicite de READ sur le compte perso).
- **D-07:** Le **scope de l'enveloppe est dérivé automatiquement** du `Account.accountType` (pas un choix utilisateur à la création). L'`owner` est rempli implicitement par le backend pour les enveloppes PERSONAL.

### Modèle d'allocation mensuelle (ENVL-02)
- **D-08:** Le champ `Envelope.budget` représente le **budget mensuel par défaut** appliqué chaque mois automatiquement. La table existante `EnvelopeAllocation` sert à **overrider un mois spécifique** (ex: budget Vacances = 200€/mois sauf juillet = 800€). Si aucune `EnvelopeAllocation` n'existe pour un mois donné, `Envelope.budget` fait foi.
- **D-09:** Le formulaire de création/édition d'enveloppe (p-dialog) est **minimaliste** : `nom`, `catégories` (multi-select), `budget par défaut`, `rollover policy` (RESET/CARRY_OVER). Pas de tableau annuel dans le form principal.
- **D-10:** Les **overrides mensuels** sont accessibles via une action dédiée sur la liste/détail d'enveloppe (bouton « Personnaliser ce mois » → dialog de saisie du montant pour un mois donné). CRUD sur `EnvelopeAllocation` réservé à cette action.

### Calcul du consumed et rollover (ENVL-03 / ENVL-04)
- **D-11:** Le `consumed` d'une enveloppe pour un mois donné est **calculé à la volée en SQL** — `SUM(transactions.amount)` + `SUM(transaction_splits.amount)` filtré sur les catégories liées (avec récursion racine→enfants) et le mois. **Aucune colonne persistée** pour le consumed. Pas de matérialisation, pas de cache applicatif. Performance acceptable à l'échelle d'un foyer (quelques milliers de transactions/mois).
- **D-12:** Le **rollover** (pour les enveloppes `CARRY_OVER`) est **calculé à la volée à la lecture** : `available_this_month = budget_this_month + (budget_prev_month - consumed_prev_month) - consumed_this_month`. Aucun job batch ni cron. Toujours cohérent avec l'état actuel des transactions (pas de divergence possible). Évaluation récursive si la chaîne dépasse 1 mois : décision à trancher par le planner — par défaut, limite le lookback à 1 mois précédent pour la v1 (un rollover n'accumule pas indéfiniment).

### Indicateurs visuels (ENVL-05)
- **D-13:** Seuils codés en dur côté front : `ratio = consumed / available` → **vert < 80%**, **jaune 80-100%**, **rouge > 100%**. Pas de configuration par enveloppe en v1. L'indicateur est un badge + progress bar PrimeNG (`p-tag` + `p-progressbar`) sur chaque ligne/card d'enveloppe.

### Historique de consommation (ENVL-06)
- **D-14:** Page dédiée `/envelopes/:id` accessible depuis la liste des enveloppes. Contenu : tableau des 12 derniers mois (colonnes : mois, budget effectif, consumed, reste, statut) + graphique d'évolution optionnel via ngx-echarts (bar chart). Routing Angular aligné sur le pattern `account-details` établi en Phase 3.

### Navigation et UX
- **D-15:** Liste des enveloppes accessible depuis `/envelopes` (entrée sidebar dédiée) ET filtrable par compte via paramètre de query `?accountId=...`. Le pattern p-table sert à la liste principale. Cohérent avec l'ergonomie Phase 4 (Categories) et Phase 5 (Transactions).

### Contrôle d'accès
- **D-16:** L'accès aux enveloppes hérite des permissions du compte lié via `AccountAccessRepository` — même pattern que `TransactionService` en Phase 5. READ sur le compte → READ sur les enveloppes ; WRITE sur le compte → WRITE sur les enveloppes. Distinction explicite 403 vs 404 (existsById) sur lookup.
- **D-17:** Création d'enveloppe exige WRITE sur le compte cible. Suppression/édition également.

### Suppression et cycle de vie
- **D-18:** **Suppression d'enveloppe** = hard delete si aucune `EnvelopeAllocation` attachée ; sinon soft delete (flag `archived` à ajouter via migration) pour préserver l'historique. Décision d'implémentation finale par le planner en fonction du volume d'historique attendu — par défaut privilégier soft delete avec flag `archived BOOLEAN NOT NULL DEFAULT FALSE` + filtre dans les queries de lecture.
- **D-19:** Archivage d'un **compte** (ACCT-05) : les enveloppes liées suivent — non listées par défaut, conservées en DB. Filtre hérite du filtre account (`bankAccount.archived = false`).

### Frontend (Angular)
- **D-20:** Structure module `envelope/` identique aux phases 3/4/5 : `envelopes.ts` (page p-table), `envelope-dialog.ts` (p-dialog création/édition), `envelope-details.ts` (page historique), `envelope.service.ts` (HttpClient + signals), `envelope.types.ts` (interfaces TypeScript).
- **D-21:** Le sélecteur multi-catégories utilise **`p-multiSelect`** PrimeNG (ou `p-treeSelect` multi) et s'intègre avec la taxonomie hiérarchique — réutilise la convention du `CategorySelector` partagé introduit en Phase 4 (extension multi-select).
- **D-22:** `p-table` sur la liste principale avec tri natif. Filtre par compte via dropdown (`p-select` des comptes accessibles à l'utilisateur). Pas de pagination serveur attendue (volume foyer faible).

### Claude's Discretion
- Structure exacte des DTOs (records Java), nommage des endpoints REST (ex: `/api/envelopes`, `/api/accounts/{id}/envelopes`)
- Implémentation exacte de la récursion catégorie racine → enfants (CTE PostgreSQL vs résolution applicative)
- Forme exacte de la requête d'agrégation consumed (native SQL vs JPQL vs Specification)
- Choix `p-multiSelect` vs `p-treeSelect` multi pour la liaison catégories (dépend de la lisibilité avec 2 niveaux)
- Soft delete via flag `archived` vs suppression en cascade (tranché selon faisabilité SQL)
- Lookback du rollover (1 mois vs récursif borné)
- Styles Tailwind pour les badges statut (vert/jaune/rouge) — cohérence avec design system PrimeNG existant

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Requirements
- `.planning/REQUIREMENTS.md` §Budgets Enveloppes — ENVL-01 à ENVL-07 (7 requirements)
- `.planning/PROJECT.md` §Key Decisions — « Enveloppes par compte (pas transversales) »

### Architecture & patterns
- `docs/adr/0002-architecture-layered.md` — Layered by feature, package `envelope/`
- `docs/agent_docs/architecture.md` — Structure backend, composants, flux de données
- `docs/agent_docs/database.md` — Schema complet PostgreSQL, relations

### Entités existantes (Phase 1)
- `backend/src/main/java/com/prosperity/envelope/Envelope.java` — Entité JPA existante (bankAccount, name, scope, owner, budget, rolloverPolicy) — à enrichir (relation catégories + éventuel archived)
- `backend/src/main/java/com/prosperity/envelope/EnvelopeAllocation.java` — Entité allocation mensuelle (envelope_id, month, allocated_amount) — à utiliser pour D-08 overrides
- `backend/src/main/java/com/prosperity/envelope/EnvelopeRepository.java` — Repository vide à enrichir avec queries access-filtered + consumed aggregation
- `backend/src/main/java/com/prosperity/envelope/EnvelopeAllocationRepository.java` — Repository vide à enrichir (findByEnvelopeAndMonth)
- `backend/src/main/java/com/prosperity/shared/EnvelopeScope.java` — Enum PERSONAL/SHARED
- `backend/src/main/java/com/prosperity/shared/RolloverPolicy.java` — Enum RESET/CARRY_OVER

### Migrations existantes
- `backend/src/main/resources/db/migration/V006__create_envelopes.sql` — Tables `envelopes` et `envelope_allocations`
- `backend/src/main/resources/db/migration/V007__migrate_money_columns_to_numeric.sql` — Colonnes `budget` et `allocated_amount` en NUMERIC(19,4)
- Dernière migration : `V013__create_recurring_templates.sql` → prochaine = V014 (envelope_categories) + éventuel V015 (archived flag)

### Patterns backend à reproduire
- `backend/src/main/java/com/prosperity/account/AccountService.java` — Pattern accès 403 vs 404, existsById
- `backend/src/main/java/com/prosperity/account/AccountAccessRepository.java` — Vérification accès (READ/WRITE/ADMIN)
- `backend/src/main/java/com/prosperity/transaction/TransactionService.java` — Pattern récent Phase 5 (filtres + Pageable + access control)
- `backend/src/main/java/com/prosperity/transaction/TransactionRepository.java` — Pattern native SQL avec CAST pour type inference PostgreSQL
- `backend/src/main/java/com/prosperity/category/CategoryRepository.java` — Lookup de catégories et hiérarchie racine/enfants

### Frontend patterns à reproduire
- `frontend/src/app/transactions/transactions.ts` — Page component récente (p-table + filtres + signals + OnPush)
- `frontend/src/app/transactions/transaction-dialog.ts` — p-dialog création/édition récent
- `frontend/src/app/categories/categories.ts` — Page à plat simple (plus proche du volume enveloppes)
- `frontend/src/app/shared/category-selector.ts` — Composant partagé UUID émis (à étendre en multi-select ou wrapper pour D-21)
- `frontend/src/app/app.routes.ts` — Routes lazy-load `/envelopes` et `/envelopes/:id` à enregistrer
- `frontend/src/app/layout/` — Sidebar à enrichir avec entrée « Enveloppes »

### Tests patterns à reproduire
- `backend/src/test/java/com/prosperity/transaction/TransactionControllerTest.java` — Tests intégration Testcontainers (access control, filtres, pagination)
- `frontend/src/app/transactions/transactions.spec.ts` — Tests composant Angular (Vitest, signals)

### Contextes phases précédentes
- `.planning/phases/03-accounts-access-control/03-CONTEXT.md` — Modèle AccountAccess, 403/404, SHARED vs PERSONAL au niveau compte
- `.planning/phases/04-categories/04-CONTEXT.md` — Taxonomie 2-niveaux, CategorySelector partagé, catégories globales au foyer
- `.planning/phases/05-transactions/05-CONTEXT.md` — Pattern CRUD + access control récent, splits, modèle Transaction complet

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `Envelope.java` : entité JPA existante, champs bankAccount/name/scope/owner/budget/rolloverPolicy prêts ; à enrichir avec relation `Set<Category> categories` (ManyToMany) et éventuel flag `archived`
- `EnvelopeAllocation.java` : entité prête pour les overrides mensuels (D-08/D-10)
- `EnvelopeScope` et `RolloverPolicy` : enums déjà définis, pas de modification
- `AccountAccessRepository.hasAccess()` + pattern 403/404 : réutilisables tel quels (D-16)
- `CategoryRepository` : findById + navigation parent/children disponible pour la récursion D-02
- `CategorySelector` (frontend) : à étendre en version multi-select (ou wrapper) pour D-21
- Transaction entity : contient `category` (ManyToOne) et `transaction_splits` est déjà une table séparée — SUM sur les deux sources possible (D-03/D-11)

### Established Patterns
- Layered architecture par feature — package `com.prosperity.envelope`
- Money en centimes via MoneyConverter → NUMERIC(19,4) en DB (standard projet)
- 403 vs 404 via existsById (pattern Phase 3/5)
- DTOs en records Java + `@Valid` sur les request bodies
- p-table + p-dialog pattern (Phase 3/4/5)
- OnPush + signals Angular 21
- Testcontainers PostgreSQL pour tests intégration

### Integration Points
- `AccountAccessRepository` → vérification accès sur toutes les mutations enveloppes (D-16/D-17)
- `CategoryRepository` → validation que category_id existe ET récupération de la hiérarchie racine→enfants (D-02)
- `Transaction.category_id` et `TransactionSplit.category_id` → sources du SUM consumed (D-11)
- Sidebar Angular (`layout/`) → ajouter lien « Enveloppes » (pattern lien Comptes / Catégories)
- `app.routes.ts` → enregistrer `/envelopes` (liste) et `/envelopes/:id` (détails)
- Phase 10 (Dashboard) consommera l'API consumed + status pour l'affichage agrégé

</code_context>

<specifics>
## Specific Ideas

- Le modèle « budget fixe avec overrides mensuels » reflète l'usage réel d'un foyer : 80% des enveloppes ont un montant stable, quelques-unes (vacances, cadeaux de fin d'année) varient
- L'indicateur visuel doit être lisible en un coup d'œil sur une carte/ligne de tableau — priorité à la cohérence avec le design system PrimeNG + Tailwind
- L'historique doit permettre de répondre à « combien ai-je dépensé en alimentation en mars ? » en 2 clics maximum
- La décision de ne pas matérialiser le consumed s'appuie explicitement sur l'échelle foyer (volume faible) — à revisiter en v2 si le projet s'ouvre à plus d'utilisateurs
- Seuils 80/100 alignés avec la convention UX budgétaire standard (YNAB, Bluecoins, etc.)

</specifics>

<deferred>
## Deferred Ideas

- **Enveloppes transversales** (cross-account) — backlog v2 confirmé (PROJECT.md)
- **Notifications** de dépassement (push, email) — NOTF-01/02, v2
- **Suggestions automatiques** de catégorisation pour imputation — CATG-05/06, v2
- **Seuils configurables** par enveloppe — différé (D-13 fixe 80/100)
- **Rollover récursif** sur plusieurs mois (accumulation indéfinie) — différé, v1 limite à 1 mois précédent
- **Compteur « hors budget »** pour transactions orphelines — différé, v2 après retours d'usage
- **Export/import** d'enveloppes ou d'historique — hors scope v1
- **Visualisation graphique avancée** (heatmap, tendances multi-mois) — graphique simple suffisant en v1

### Reviewed Todos (not folded)
Aucun todo pending ne correspondait à cette phase (vérifié via `gsd-tools todo match-phase 6`).

</deferred>

---

*Phase: 06-envelope-budgets*
*Context gathered: 2026-04-22*
