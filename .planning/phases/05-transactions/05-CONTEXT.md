# Phase 5: Transactions - Context

**Gathered:** 2026-04-06 (assumptions mode)
**Status:** Ready for planning

<domain>
## Phase Boundary

Users can manage their financial transactions manually with full CRUD, search, and reconciliation support. This phase covers manual entry, edit, delete, recurring templates, pointage (manual reconciliation), split transactions, search/filter, and paginated listing. Plaid import is Phase 7 — this phase only handles the MANUAL source and the reconciliation UX that prepares the domain for Plaid data.

</domain>

<decisions>
## Implementation Decisions

### Transaction CRUD & Data Model (TXNS-01/02/03)
- **D-01:** L'entité `Transaction` est complète pour le CRUD de base — tous les champs requis existent déjà (`amount`, `transactionDate`, `description`, `category`, `bankAccount`, `source`, `state`, `pointed`). Aucune migration DB pour le CRUD simple.
- **D-02:** Montants en centimes (`long`/`NUMERIC`) via `MoneyConverter` — aucun float. Pattern établi en Phase 1, non négociable.
- **D-03:** `source` = `TransactionSource.MANUAL` pour les transactions saisies manuellement (vs `PLAID`, `RECURRING`). Ce champ est déjà l'enum dans `shared/TransactionSource.java`.

### Split de transactions (TXNS-06)
- **D-04:** Nouvelle table `transaction_splits` + entité `TransactionSplit` requis. La colonne `category_id` actuelle est un FK unique — impossible de stocker plusieurs allocations catégorie/montant sans table dédiée.
- **D-05:** Structure proposée : `transaction_splits(id, transaction_id FK, category_id FK, amount NUMERIC, description VARCHAR)`. La somme des splits doit égaler le montant de la transaction parente.
- **D-06:** Une transaction avec splits actifs a son `category_id` mis à null (le split remplace la catégorie unique). Le service valide la cohérence somme = montant total avant persistance.

### Templates récurrents (TXNS-04)
- **D-07:** Nouvelle entité `RecurringTemplate` + migration V012 requise. `TransactionSource.RECURRING` existe dans l'enum mais n'est pas implémenté — c'est ici qu'on l'utilise.
- **D-08:** Champs du template : `account_id`, `amount`, `description`, `category_id`, `frequency` (enum : WEEKLY/MONTHLY/YEARLY), `day_of_month` (INT, pour fréquence mensuelle), `next_due_date` (LocalDate), `active` (boolean).
- **D-09:** "Générer depuis template" crée une vraie `Transaction` avec `source = RECURRING` et met à jour `next_due_date` sur le template. Pas de génération automatique (batch) en Phase 5 — l'utilisateur déclenche manuellement.

### Contrôle d'accès (sécurité)
- **D-10:** L'accès aux transactions hérite des permissions du compte lié (`AccountAccess`). CRUD sur une transaction exige au minimum `WRITE` sur `transaction.bankAccount`. Lecture exige `READ`.
- **D-11:** `TransactionService` doit intégrer `AccountAccessRepository` avec le même pattern que `AccountService` : distinction explicite 403 (accès refusé) vs 404 (transaction inexistante).
- **D-12:** La vérification d'accès actuelle dans `TransactionService` est absente — c'est un gap de sécurité connu à combler dans cette phase.

### Pagination & Filtres (TXNS-07/08)
- **D-13:** `Spring Data JPA Pageable` + query JPQL avec filtres optionnels, retourne `Page<Transaction>`. Premier usage de pagination dans le projet.
- **D-14:** Filtres supportés : `accountId` (obligatoire), `dateFrom`, `dateTo`, `amountMin`, `amountMax`, `categoryId`, `search` (full-text sur `description`). Tous optionnels sauf `accountId`.
- **D-15:** Tri par défaut : `transactionDate DESC`. Page size par défaut : 20.
- **D-16:** L'endpoint est scopé par compte : `GET /api/accounts/{accountId}/transactions?page=0&size=20&...`. Pas de liste cross-comptes en Phase 5 (réservé au Dashboard Phase 10).

### Frontend (Angular)
- **D-17:** Structure module identique aux phases 3/4 : `transactions.ts` (page + `p-table` paginée), `transaction-dialog.ts` (create/edit en `p-dialog`), `transaction.service.ts` (signals + HttpClient), `transaction.types.ts` (interfaces TypeScript).
- **D-18:** `CategorySelector` partagé (`frontend/src/app/shared/category-selector.ts`) réutilisé directement — émet `string | null` (UUID). Aucune modification nécessaire.
- **D-19:** `p-table` avec pagination serveur (`[lazy]="true"`, `(onLazyLoad)="loadTransactions($event)"`). Les filtres sont des champs de formulaire au-dessus de la table, pas des filtres inline de p-table.
- **D-20:** Pas d'interface frontend pour les splits et templates récurrents dans cette phase si la complexité est trop élevée — le périmètre minimal requis est TXNS-01/02/03/07/08. TXNS-04/05/06 sont inclus si le temps le permet mais peuvent être découpés en sous-plans dédiés.

### Pointage / Réconciliation (TXNS-05)
- **D-21:** Le champ `pointed: boolean` existant suffit pour le pointage manuel. L'utilisateur coche/décoche "pointé" sur une transaction — cela met `pointed = true`.
- **D-22:** `TransactionState.MATCHED` sera utilisé en Phase 7 (Plaid) pour lier une saisie manuelle à un import. En Phase 5, seul `MANUAL_UNMATCHED` est le state initial des transactions manuelles.
- **D-23:** Les concepts sont orthogonaux : `state` gère le cycle de vie Plaid (unmatched/matched), `pointed` gère la confirmation bancaire manuelle de l'utilisateur.

### Claude's Discretion
- Exact JPQL query structure for filtering (dynamic predicates vs named params)
- Transaction form layout within dialog (field order, date picker format)
- Error messages and form validation UX
- RecurringTemplate API endpoint design (REST resource sous `/api/recurring-templates` ou sous `/api/accounts/{id}/recurring-templates`)

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Requirements
- `.planning/REQUIREMENTS.md` §Transactions — TXNS-01 à TXNS-08 (8 requirements à couvrir)

### Domain Model & Migrations
- `backend/src/main/java/com/prosperity/transaction/Transaction.java` — Entité existante, champs et relations
- `backend/src/main/java/com/prosperity/shared/TransactionState.java` — Enum états reconciliation
- `backend/src/main/java/com/prosperity/shared/TransactionSource.java` — Enum MANUAL/PLAID/RECURRING
- `backend/src/main/resources/db/migration/V005__create_transactions.sql` — Schema actuel transactions
- `backend/src/main/resources/db/migration/V011__seed_plaid_categories.sql` — Dernière migration (V011 → V012 sera transaction_splits ou recurring_templates)

### Patterns établis à reproduire
- `backend/src/main/java/com/prosperity/account/AccountService.java` — Pattern accès 403 vs 404
- `backend/src/main/java/com/prosperity/account/AccountAccessRepository.java` — Pattern vérification accès
- `backend/src/main/java/com/prosperity/category/CategoryController.java` — Pattern REST controller (records, @Valid, error handlers)
- `backend/src/main/java/com/prosperity/category/CategoryService.java` — Pattern service avec exception métier

### Frontend patterns à reproduire
- `frontend/src/app/categories/categories.ts` — Page component pattern (p-table, signals, OnPush)
- `frontend/src/app/categories/category-dialog.ts` — Dialog create/edit pattern
- `frontend/src/app/categories/category.service.ts` — Service pattern (HttpClient + signals)
- `frontend/src/app/shared/category-selector.ts` — Composant partagé réutilisable (UUID émis)
- `frontend/src/app/app.routes.ts` — Routing lazy-load pattern

### Tests patterns à reproduire
- `backend/src/test/java/com/prosperity/category/CategoryControllerTest.java` — Tests intégration (Testcontainers)
- `frontend/src/app/categories/categories.spec.ts` — Tests composant Angular (Vitest)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `Transaction` entity : complète pour CRUD de base, aucun ajout requis
- `TransactionRepository` : actuellement basique, à enrichir avec requêtes filtrées + Pageable
- `TransactionService` : stub minimal (PATCH category seulement), à compléter
- `TransactionController` : stub minimal, à compléter
- `CategorySelector` (frontend) : prêt à l'emploi, émet UUID string
- `AccountAccessRepository.hasAccess()` : méthode réutilisable pour vérification accès

### Established Patterns
- Layered architecture par feature (Controller / Service / Repository) — respecter strictement
- Money en centimes via `MoneyConverter` — aucune exception
- Distinctions 403 vs 404 via `existsById` check — pattern `AccountService` à copier
- `@Valid` sur les request bodies + records Java pour DTOs
- OnPush + signals Angular 21 — pas de zone.js state management
- `p-table` lazy server-side pagination — nouveau pattern à établir

### Integration Points
- `AccountAccessRepository` → vérification accès sur toutes les mutations transactions
- `CategoryRepository` → validation que category_id existe avant assignation
- `AccountRepository` → validation que accountId existe et accès OK avant création transaction
- `CategorySelector` frontend → réutilisation directe dans transaction-dialog
- Routes Angular → ajouter `/accounts/:id/transactions` dans `app.routes.ts`

</code_context>

<specifics>
## Specific Ideas

- L'endpoint transactions est scopé par compte : `GET /api/accounts/{accountId}/transactions` — pas de liste cross-comptes en Phase 5
- Le "pointage" est un simple toggle boolean — pas une transition de state complexe
- La génération depuis template est manuelle (bouton) — pas de batch automatique en Phase 5
- Splits : la somme des parts doit = montant total de la transaction parente (validation service)

</specifics>

<deferred>
## Deferred Ideas

- Batch automatique pour templates récurrents (génération planifiée) — Phase 7 ou backlog
- Suggestion automatique de pointage (montant + date proches) — PLAD-09, v2 requirement
- Liste cross-comptes des transactions — Phase 10 (Dashboard)
- Import Plaid et transition pending→posted — Phase 7
- Regles de catégorisation automatique — CATG-05, v2

None — discussion stayed within phase scope.

</deferred>

---

*Phase: 05-transactions*
*Context gathered: 2026-04-06*
