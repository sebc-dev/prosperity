# Phase 6: Envelope Budgets - Research

**Researched:** 2026-04-22
**Domain:** Per-account budget envelopes (N:N category linking, on-the-fly consumed aggregation, lazy rollover, visual status indicators)
**Confidence:** HIGH (stack and patterns all confirmed from existing codebase + verified 2026 sources)

## Summary

Phase 6 introduces envelope budgeting on top of the already-stable transaction + category + access-control domain. The work is predominantly **domain/service code** reusing Phase 3/5 patterns (403 vs 404 access control, native SQL for aggregation, signals + p-table on the frontend). The one genuinely new backend problem is the **consumed aggregation query** — a `SUM` over `transactions.amount` AND `transaction_splits.amount` scoped to an envelope's categories (root + children) for a given `YearMonth`. The frontend work is a standard list/dialog/detail triptych that extends the existing `CategorySelector` into a multi-select variant and wires a status badge/progressbar into each row.

The CONTEXT.md has locked 22 decisions, so research is constrained: no "which library" exploration. Focus is on *how* to execute the locked decisions cleanly within the existing stack.

**Primary recommendation:**

1. Model `Envelope.categories` as `@ManyToMany` with a junction table `envelope_categories(envelope_id, category_id)` using a composite primary key (no extra columns → no `@EmbeddedId` needed on a separate entity).
2. Implement the consumed query as a single **native SQL `UNION ALL`** over `transactions` (where `category_id IS NOT NULL` and no split override) and `transaction_splits` — both filtered through a PostgreSQL **recursive CTE** that expands envelope category roots into root+children. Keep it in `EnvelopeRepository` alongside the existing `TransactionRepository` native-SQL pattern (with `CAST(:param AS uuid)` for parameter type inference).
3. Compute rollover **lazily at read time** (D-12) with **1-month lookback** only in v1. Expose a pure-function service method `computeAvailable(envelope, month)` that fetches `budget(month)`, `consumed(month)`, and for `CARRY_OVER` envelopes also `budget(month-1)` and `consumed(month-1)`.
4. Soft delete via `archived BOOLEAN NOT NULL DEFAULT FALSE` on `envelopes` (V014 migration). Filter `archived = false` in read queries.
5. Extend `CategorySelector` to accept `selectionMode="checkbox"` (PrimeNG `p-treeSelect` already supports hierarchical multi-select with checkboxes). Do **not** fork into a second component.

## Project Constraints (from CLAUDE.md)

These directives have the same authority as CONTEXT.md locked decisions:

- **Open source licensing:** all new deps MUST be MIT or Apache 2.0. `ngx-echarts` and Apache ECharts are both Apache 2.0 — safe. Any other new library must be verified.
- **Stack locked:** Java 21 LTS + Spring Boot 4.0.x + Spring Data JPA 4.0.x + Flyway 11.x + PostgreSQL 17 + Angular 21 + PrimeNG 21 + Tailwind v4. No bleeding-edge substitutions.
- **Connecteur bancaire abstrait:** N/A for Phase 6 (no Plaid coupling introduced).
- **Review:** atomic phase decoupling — plans must be reviewable in small increments.
- **Testing principles (.claude/rules/testing-principles.md):**
  - AAA structure, Act on **one line**, names describe scenario + expected result in snake_case
  - Test **observable behavior**, not implementation
  - FIRST: fast (< 100ms unit), isolated, repeatable, self-validating, timely
  - Minimal doubles (≤ 2-3); prefer real collaborators and fakes over mocks
  - Test Data Builders pattern, DAMP > DRY in test scenarios
  - No flaky patterns (no sleep, no `Date.now()`, no real network)
- **GSD workflow:** planning must emit atomic PLAN.md per concern (data layer / service / controller / frontend / tests). No direct repo edits outside GSD workflow.
- **JaCoCo coverage enforced:** 70% instruction, 50% branch — Phase 6 must maintain these thresholds.
- **Checkstyle + google-java-format + SonarQube + OWASP:** all quality gates remain active.

## User Constraints (from CONTEXT.md)

### Locked Decisions

**Liaison enveloppe ↔ catégories (ENVL-03):**
- **D-01:** Relation **N:N** via nouvelle table de jonction `envelope_categories (envelope_id FK, category_id FK, PRIMARY KEY composite)`. Contrainte métier : **une catégorie ne peut être liée qu'à UNE enveloppe par compte** — validation au service.
- **D-02:** Lier une **catégorie racine** embrasse automatiquement ses **sous-catégories**. Récursion via recursive CTE ou `IN (parent_id, children_ids)` résolu côté service.
- **D-03:** Les **splits de transaction** sont imputés **au prorata** : chaque ligne de `transaction_splits` impute l'enveloppe liée à la catégorie de ce split pour son montant partiel. SUM consumed = `transactions.category_id` ET `transaction_splits` (UNION ou JOIN avec CASE).
- **D-04:** Une transaction dont la catégorie n'est liée à **aucune enveloppe** est **ignorée silencieusement**. Pas de compteur « hors budget » en v1.

**Visibilité et portée (blocker STATE.md résolu):**
- **D-05:** Sur un compte **SHARED**, toutes les enveloppes sont `scope=SHARED, owner=null`. Un seul set d'enveloppes par compte commun.
- **D-06:** Sur un compte **PERSONAL**, les enveloppes sont `scope=PERSONAL, owner=user_du_compte`. Visibilité = règles existantes `AccountAccessRepository`.
- **D-07:** Le **scope est dérivé automatiquement** du `Account.accountType` (pas un choix utilisateur). `owner` rempli implicitement par le backend pour PERSONAL.

**Modèle d'allocation mensuelle (ENVL-02):**
- **D-08:** `Envelope.budget` = budget mensuel par défaut. `EnvelopeAllocation` = override pour un mois spécifique. Si pas d'allocation pour un mois, `Envelope.budget` fait foi.
- **D-09:** Formulaire création/édition minimaliste : `nom`, `catégories` (multi-select), `budget par défaut`, `rollover policy`. Pas de tableau annuel.
- **D-10:** Les overrides mensuels via action dédiée (bouton « Personnaliser ce mois ») → dialog de saisie par mois.

**Calcul consumed et rollover (ENVL-03/04):**
- **D-11:** `consumed` calculé à la volée en SQL. Aucune colonne persistée. Pas de matérialisation ni cache.
- **D-12:** Rollover (`CARRY_OVER`) calculé à la volée à la lecture : `available_this_month = budget_this_month + (budget_prev_month - consumed_prev_month) - consumed_this_month`. **Limite v1 : 1 mois de lookback**.

**Indicateurs visuels (ENVL-05):**
- **D-13:** Seuils codés en dur côté front : `ratio = consumed / available` → **vert < 80%**, **jaune 80-100%**, **rouge > 100%**. Badge + progress bar PrimeNG.

**Historique (ENVL-06):**
- **D-14:** Page dédiée `/envelopes/:id` — tableau 12 derniers mois + graphique optionnel ngx-echarts (bar chart).

**Navigation et UX:**
- **D-15:** Liste `/envelopes` (entrée sidebar) + filtrable par `?accountId=...`. `p-table` PrimeNG.

**Contrôle d'accès:**
- **D-16:** Héritage via `AccountAccessRepository`. READ/WRITE 403 vs 404 (existsById) — pattern `TransactionService` Phase 5.
- **D-17:** Création/suppression/édition exigent WRITE sur le compte.

**Suppression et cycle de vie:**
- **D-18:** Soft delete par défaut via flag `archived BOOLEAN NOT NULL DEFAULT FALSE` + filtre dans les queries. Hard delete possible si aucune allocation attachée.
- **D-19:** Archivage compte : enveloppes liées suivent le filtre `bankAccount.archived = false`.

**Frontend (Angular):**
- **D-20:** Structure module `envelope/` identique phases 3/4/5 : `envelopes.ts`, `envelope-dialog.ts`, `envelope-details.ts`, `envelope.service.ts`, `envelope.types.ts`.
- **D-21:** Sélecteur multi-catégories via `p-multiSelect` OU `p-treeSelect` multi — réutilise `CategorySelector` partagé.
- **D-22:** `p-table` liste principale avec tri natif. Dropdown filtre compte (`p-select`). Pas de pagination serveur.

### Claude's Discretion

- Structure exacte DTOs (records Java), nommage endpoints REST
- Récursion racine → enfants : CTE PostgreSQL vs résolution applicative
- Forme exacte requête consumed : native SQL vs JPQL vs Specification
- `p-multiSelect` vs `p-treeSelect` multi (lisibilité)
- Soft delete `archived` vs cascade
- Lookback rollover (1 mois vs récursif borné — v1 fixe à 1)
- Styles Tailwind badges statut (vert/jaune/rouge)

### Deferred Ideas (OUT OF SCOPE)

- Enveloppes transversales (cross-account) — v2
- Notifications de dépassement (NOTF-01/02) — v2
- Suggestions auto de catégorisation (CATG-05/06) — v2
- Seuils configurables par enveloppe (D-13 fixe 80/100)
- Rollover récursif multi-mois
- Compteur « hors budget » pour transactions orphelines
- Export/import
- Heatmaps, graphiques avancés

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| ENVL-01 | Utilisateur peut créer une enveloppe sur un compte | Envelope entity + ManyToMany categories (D-01) + scope derivation (D-07) ; REST POST `/api/accounts/{id}/envelopes` ; WRITE access (D-17) |
| ENVL-02 | Utilisateur peut allouer un montant mensuel | `Envelope.budget` (default) + `EnvelopeAllocation` override (D-08, D-10) ; UNIQUE(envelope_id, month) already in V006 |
| ENVL-03 | Les dépenses catégorisées sont imputées à l'enveloppe | Consumed query = SUM over transactions + transaction_splits filtered by envelope's category tree (D-02, D-03, D-11) |
| ENVL-04 | Rollover paramétrable (report auto ou remise à zéro) | `rolloverPolicy` enum exists ; lazy formula at read (D-12) ; 1-month lookback v1 |
| ENVL-05 | Indicateur visuel dépassement (rouge/jaune) | Frontend `p-tag` + `p-progressbar` avec seuils 80%/100% (D-13) |
| ENVL-06 | Utilisateur peut voir l'historique de consommation | Page `/envelopes/:id` — 12 derniers mois + optional ngx-echarts bar chart (D-14) |
| ENVL-07 | Utilisateur peut modifier ou supprimer une enveloppe | PUT/DELETE endpoints ; soft delete via `archived` flag (D-18) ; WRITE access (D-17) |

## Standard Stack

### Core (already in project — no new deps)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Spring Boot | 4.0.5 | Backend framework | Already in use (pom.xml parent) |
| Spring Data JPA | 4.0.x (via Boot) | ORM | Already in use — `@ManyToMany` + native SQL well-supported |
| Hibernate | 7.x (via Boot 4) | JPA provider | Auto-configured; supports `@ManyToMany` composite-key join tables natively |
| Flyway | 11.x | Migrations | Already in use — next migration V014 |
| PostgreSQL | 17 | Database | Already in use; `WITH RECURSIVE` CTE fully supported |
| Testcontainers | 2.0.0 | Tests intégration | Already in use (TestcontainersConfig.java) |
| AssertJ | via spring-boot-starter-test | Assertions | Already used in TransactionControllerTest |
| JUnit | 5.x | Test framework | Already used |
| Angular | 21.2.x | Frontend SPA | Already in use |
| PrimeNG | 21.1.4 | UI components | Already in use (TableModule, TagModule, ProgressBarModule, TreeSelectModule) |
| Tailwind CSS | v4.2.2 | Utility CSS | Already in use |

### Supporting — Optional (evaluated)
| Library | Version | Purpose | Decision |
|---------|---------|---------|----------|
| ngx-echarts | 21.0.0 | Bar chart for history page | **Optional per D-14**. Not currently in package.json. If the planner decides to add the chart in v1, add `ngx-echarts` + `echarts` (both Apache 2.0). Otherwise, render the 12-month history as a `p-table` only and defer chart to Phase 10 dashboard. **Recommendation: defer chart to Phase 10** — keeps Phase 6 focused and aligned with "atomic decoupling" constraint. |

### Alternatives Considered (all rejected — CONTEXT.md locks)

| Instead of | Rejected alternative | Reason |
|------------|----------------------|--------|
| Soft delete via `archived` flag | JPA `@SoftDelete` (Hibernate 6.4+) | D-18 specifies manual flag + query filter; `@SoftDelete` adds reflection opacity and would require tests to confirm filter interaction with N:N junction |
| Consumed in-query | Materialized column `consumed_cents` | D-11 explicit: no persisted column, no cache |
| Rollover batch job | Lazy compute at read | D-12 explicit: no cron |
| Cross-account envelopes | Per-account envelopes | PROJECT.md Key Decision |

**Installation:** No new backend Maven dependencies required. No new frontend npm dependencies required (unless ngx-echarts is added; see above).

**Version verification:** All used versions verified against existing pom.xml and package.json at time of research. Spring Boot 4.0.5 (confirmed pom.xml), PrimeNG 21.1.4 (package.json ^21.1.4), Testcontainers 2.0.0 (pom.xml property), Angular 21.2 (package.json ^21.2.0).

## Architecture Patterns

### Recommended Structure (mirrors Phase 5 transaction/)

```
backend/src/main/java/com/prosperity/envelope/
├── Envelope.java                         # existing — add @ManyToMany categories + archived
├── EnvelopeAllocation.java               # existing — no change
├── EnvelopeCategory.java                 # OPTIONAL — see Pattern 1 below
├── EnvelopeRepository.java               # enrich with access-filtered queries + consumed aggregation
├── EnvelopeAllocationRepository.java     # enrich with findByEnvelopeAndMonth, findByEnvelopeAndMonthRange
├── EnvelopeService.java                  # NEW — CRUD + consumed + rollover computation
├── EnvelopeController.java               # NEW — REST endpoints
├── EnvelopeResponse.java                 # NEW record DTO (includes computed available/consumed/status)
├── CreateEnvelopeRequest.java            # NEW record
├── UpdateEnvelopeRequest.java            # NEW record (partial PATCH semantics)
├── EnvelopeAllocationRequest.java        # NEW record for monthly override
├── EnvelopeHistoryEntry.java             # NEW record (month, budget, consumed, status)
├── EnvelopeNotFoundException.java        # NEW
├── DuplicateEnvelopeCategoryException.java  # NEW (D-01 constraint violation)
└── EnvelopeStatus.java                   # enum GREEN/YELLOW/RED — computed server-side for consistency

backend/src/main/resources/db/migration/
├── V014__create_envelope_categories.sql  # junction table
└── V015__add_archived_to_envelopes.sql   # soft delete flag

frontend/src/app/envelopes/
├── envelopes.ts              # p-table list page, filter by account
├── envelope-dialog.ts        # p-dialog create/edit with multi-select categories
├── envelope-details.ts       # /envelopes/:id history page
├── envelope.service.ts       # signals + HttpClient
├── envelope.types.ts         # interfaces
├── envelopes.spec.ts
├── envelope-dialog.spec.ts
├── envelope-details.spec.ts
└── envelope.service.spec.ts

frontend/src/app/shared/
└── category-selector.ts      # EXTEND with multi-select mode (see Pattern 5)
```

### Pattern 1: `@ManyToMany` Simple (no extra columns) — PREFERRED

Because the junction table stores **only** `envelope_id` and `category_id` (composite PK, no extra columns like "weight" or "order"), the simplest idiomatic Spring Data JPA modeling is:

```java
// Source: Baeldung "Many-To-Many Relationship in JPA" + verified against Envelope.java existing style
@Entity
@Table(name = "envelopes")
public class Envelope {
  // ... existing fields ...

  @ManyToMany(fetch = FetchType.LAZY)
  @JoinTable(
      name = "envelope_categories",
      joinColumns = @JoinColumn(name = "envelope_id"),
      inverseJoinColumns = @JoinColumn(name = "category_id"))
  private Set<Category> categories = new HashSet<>();

  public Set<Category> getCategories() { return categories; }
  public void setCategories(Set<Category> categories) { this.categories = categories; }
}
```

**No need for a separate `EnvelopeCategory` entity** — Hibernate manages the junction automatically. This is the "best way to map a simple many-to-many association" (Vlad Mihalcea).

**Alternative (rejected for this case):** `@Entity` on a junction class with `@EmbeddedId` composite key — only needed when the junction has extra columns. Adds boilerplate without value.

**One caveat:** When removing/replacing categories, the `Set` reference must be mutated (`envelope.getCategories().clear(); envelope.getCategories().addAll(newCategories);`) rather than reassigned — or Hibernate will track the wrong collection. This is a classic pitfall (see Pitfall 3 below).

### Pattern 2: Access-Filtered Repository Queries (copy from Phase 5)

```java
// Source: existing AccountRepository.findByIdAndUserId pattern
public interface EnvelopeRepository extends JpaRepository<Envelope, UUID> {

  /** Returns non-archived envelopes for a single account, filtered by user access. */
  @Query("""
      SELECT e FROM Envelope e
      JOIN e.bankAccount ba
      JOIN AccountAccess aa ON aa.bankAccount = ba
      WHERE aa.user.id = :userId
      AND ba.id = :accountId
      AND e.archived = false
      AND ba.archived = false
      ORDER BY e.name ASC
      """)
  List<Envelope> findByAccountAccessibleToUser(
      @Param("accountId") UUID accountId, @Param("userId") UUID userId);

  /** Returns all non-archived envelopes accessible to the user across all their accounts. */
  @Query("""
      SELECT e FROM Envelope e
      JOIN e.bankAccount ba
      JOIN AccountAccess aa ON aa.bankAccount = ba
      WHERE aa.user.id = :userId
      AND e.archived = false
      AND ba.archived = false
      ORDER BY ba.name ASC, e.name ASC
      """)
  List<Envelope> findAllAccessibleToUser(@Param("userId") UUID userId);
}
```

Then in the service, for per-envelope access checks, **reuse the existing `AccountAccessRepository.hasAccess()` via `AccountRepository.hasAccess()`** exactly as `TransactionService` does (lines 379-388). Do NOT introduce a new access mechanism — the account is the trust boundary.

### Pattern 3: Consumed Aggregation (Native SQL with Recursive CTE)

This is the one novel query. Requirement: for a given envelope and month, sum all transaction-amount-equivalents that impute this envelope's categories (root + children, per D-02), pulling from both `transactions.category_id` (when the transaction is not split) AND `transaction_splits.amount` (when split, the transaction's own category is nullified per Phase 5 D-06).

```sql
-- Source: PostgreSQL WITH Queries docs + existing TransactionRepository native SQL style
WITH RECURSIVE envelope_cat_tree AS (
    -- Base: direct categories of the envelope
    SELECT c.id
    FROM envelope_categories ec
    JOIN categories c ON c.id = ec.category_id
    WHERE ec.envelope_id = CAST(:envelopeId AS uuid)

    UNION ALL

    -- Recursion: children of any category already in the set
    SELECT child.id
    FROM categories child
    JOIN envelope_cat_tree parent ON child.parent_id = parent.id
)
SELECT COALESCE(SUM(subquery.amount), 0) AS consumed
FROM (
    -- Transactions with a direct category and no splits
    SELECT t.amount
    FROM transactions t
    WHERE t.bank_account_id = CAST(:accountId AS uuid)
      AND t.category_id IN (SELECT id FROM envelope_cat_tree)
      AND t.transaction_date >= CAST(:monthStart AS date)
      AND t.transaction_date < CAST(:nextMonthStart AS date)

    UNION ALL

    -- Transaction splits (transaction.category is null by Phase 5 D-06)
    SELECT ts.amount
    FROM transaction_splits ts
    JOIN transactions t ON t.id = ts.transaction_id
    WHERE t.bank_account_id = CAST(:accountId AS uuid)
      AND ts.category_id IN (SELECT id FROM envelope_cat_tree)
      AND t.transaction_date >= CAST(:monthStart AS date)
      AND t.transaction_date < CAST(:nextMonthStart AS date)
) subquery;
```

**Why native SQL and not JPQL:**
- JPQL lacks `WITH RECURSIVE` CTE support (Hibernate 7 does **not** parse recursive CTEs in HQL — they require native SQL).
- The `UNION ALL` between transactions and splits is more natural in native SQL.
- Existing `TransactionRepository.findByFilters` already sets the precedent for native SQL with `CAST(:param AS uuid)` for PostgreSQL parameter type inference.

**Why `CAST(:param AS uuid)`:** PostgreSQL cannot infer types for bind parameters used in certain contexts. The existing `TransactionRepository.java` proves this pattern is required; copy it verbatim.

**Expense convention:** Transaction amounts are signed (negative for spending, positive for income). The "consumed" for a budget envelope should be the **absolute value of negative amounts** (or equivalently, `-SUM(amount)` where amount < 0). The planner should clarify the sign convention in PLAN — either:
- Filter `WHERE amount < 0` and take `-SUM(amount)` (treats only spending), OR
- Take raw `SUM(amount)` and let the formula operate in signed math (budget remaining = budget + SUM(negatives) + SUM(positives))

Recommendation: **filter `amount < 0` and return positive consumed**, aligned with user mental model "j'ai dépensé 250€". Refunds to a spending category (positive transactions on a negative-expected category) are edge cases — document them out of scope or add as test.

**Alternative (applicative resolution) — rejected:** resolve root → children in a Java service pre-step (single JPQL `Category c WHERE c.id IN :roots OR c.parent.id IN :roots`), then pass the flat `IN` list to a simpler query. Pros: simpler SQL, no CTE. Cons: two round-trips, couples service to category taxonomy depth limit (2 levels, CATG-04). **Recommendation: use the CTE** — self-contained query, future-proof if taxonomy ever deepens, and PostgreSQL handles it efficiently with an index on `categories.parent_id`.

### Pattern 4: Rollover Computation (Service-Layer, Pure Function)

```java
// Pseudocode — not yet written
public Money computeAvailable(Envelope envelope, YearMonth month) {
  Money budgetThisMonth = resolveBudget(envelope, month);         // allocation override OR envelope.budget
  Money consumedThisMonth = aggregateConsumed(envelope, month);   // native SQL above

  Money baseAvailable = budgetThisMonth.subtract(consumedThisMonth);

  if (envelope.getRolloverPolicy() == RolloverPolicy.RESET) {
    return baseAvailable;
  }

  // CARRY_OVER — 1 month lookback only (D-12 v1)
  YearMonth previous = month.minusMonths(1);
  Money budgetPrev = resolveBudget(envelope, previous);
  Money consumedPrev = aggregateConsumed(envelope, previous);
  Money carryOver = budgetPrev.subtract(consumedPrev);

  // Only carry over positive remainder (overspend does NOT propagate forward in v1)
  if (carryOver.amount().signum() < 0) {
    carryOver = Money.zero();
  }

  return baseAvailable.add(carryOver);
}

private Money resolveBudget(Envelope envelope, YearMonth month) {
  return envelopeAllocationRepository
      .findByEnvelopeIdAndMonthValue(envelope.getId(), month.atDay(1))
      .map(EnvelopeAllocation::getAllocatedAmount)
      .orElse(envelope.getBudget());
}
```

**Design notes:**
- The function is a **pure** composition of 4 query results (2 budget lookups, 2 consumed queries). Easy to unit-test with a stubbed repository.
- Planner should consider cost: 4 queries per envelope per page load. For a dashboard showing 20 envelopes, this is 80 queries — acceptable at foyer scale (D-11 explicitly accepts this tradeoff). If latency is observed, batch-optimize in a later phase (out of scope Phase 6).
- **Negative carry-over policy (overspend from previous month):** the formula above treats negative `carryOver` as zero. Alternative: propagate negative (starts the month already in the red). CONTEXT.md doesn't specify — recommend planner ask user, but default to **zero-clamping** (YNAB-style: "you can't overspend into the past; the hole is realized this month and you must cover it").

### Pattern 5: Extend `CategorySelector` for Multi-Select — PREFERRED OVER FORK

`p-treeSelect` supports multi-select with checkboxes natively (`selectionMode="checkbox"`). The existing `CategorySelector` (`frontend/src/app/shared/category-selector.ts`) already uses `p-treeSelect` in single mode. The cleanest path:

```typescript
// Source: PrimeNG treeselect docs — verified from primeng.org/treeselect
// Extension pattern:
@Component({...})
export class CategorySelector {
  options = input.required<TreeNode[]>();
  placeholder = input('Categorie parente (optionnel)');
  selectionMode = input<'single' | 'checkbox'>('single');

  // For single mode:
  categorySelected = output<string | null>();

  // For multi mode:
  categoriesChanged = output<string[]>();

  // Template conditional renders the right p-treeselect config
}
```

**Why `p-treeSelect` over `p-multiSelect`:**
- The category taxonomy is inherently **hierarchical** (2 levels, root → children). `p-treeSelect` visualizes the hierarchy as a tree with parent-toggles-all-children behavior.
- Already in use in transactions filter (transactions.ts line 82). Consistency principle.
- `p-multiSelect` would require flattening with manual indentation — worse UX.

**PrimeNG 21 `p-treeSelect` multi-select confirmed:** supports `selectionMode="checkbox"` (or `"multiple"`). Selected items separated by comma, overflow shows ellipsis. `metaKeySelection=false` for click-to-add (no ⌘ required).

**CategorySelector emission pattern:** in multi mode, emit `string[]` (UUIDs). Consumer binds to a signal: `protected selectedCategoryIds = signal<string[]>([])`. Keep naming consistent with existing single-mode `categorySelected` output.

### Pattern 6: Visual Status — Server-Computed OR Client-Computed?

**Recommendation: Compute on server, send in response DTO.**

Pros of server computation:
- Single source of truth for thresholds (eases tests and future changes)
- Dashboard (Phase 10) can reuse without duplicating logic
- Keeps frontend thin — template just maps `status → severity`

```java
public enum EnvelopeStatus { GREEN, YELLOW, RED }

// In EnvelopeService
private EnvelopeStatus computeStatus(Money available, Money budget) {
  BigDecimal budgetAmount = budget.amount();
  if (budgetAmount.signum() <= 0) return EnvelopeStatus.GREEN; // defensive
  BigDecimal consumed = budget.subtract(available).amount();
  BigDecimal ratio = consumed.divide(budgetAmount, 4, RoundingMode.HALF_UP);
  if (ratio.compareTo(new BigDecimal("1.00")) > 0) return EnvelopeStatus.RED;
  if (ratio.compareTo(new BigDecimal("0.80")) >= 0) return EnvelopeStatus.YELLOW;
  return EnvelopeStatus.GREEN;
}
```

**Frontend mapping** (`envelopes.ts` template):

```typescript
// p-tag severity mapping:
// GREEN -> success
// YELLOW -> warn
// RED -> danger

<p-tag [value]="envelope.status" [severity]="statusSeverity(envelope.status)" />
<p-progressbar
  [value]="envelope.consumedPercentage"
  [styleClass]="progressBarClass(envelope.status)"
/>

statusSeverity(s: 'GREEN' | 'YELLOW' | 'RED'): 'success' | 'warn' | 'danger' {
  return s === 'GREEN' ? 'success' : s === 'YELLOW' ? 'warn' : 'danger';
}
```

Tailwind classes for progress bar if theming needs override (PrimeNG p-progressbar takes a single `value` 0-100 and supports `styleClass` for color customization).

### Anti-Patterns to Avoid

- **Persisted `consumed` column** — explicitly rejected by D-11. Anyone proposing "materialize for performance" must justify against foyer-scale constraint.
- **Batch cron for rollover** — explicitly rejected by D-12. Lazy eval only.
- **Duplicate access check logic** — reuse `AccountAccessRepository.hasAccess()` via `AccountRepository.hasAccess()` exactly like `TransactionService.requireAccountAccess()`.
- **Service touching `SecurityContextHolder`** — pattern from AccountService/TransactionService: controller extracts `Principal.getName()`, passes as `String userEmail` argument. Do not break this convention.
- **Reassigning `@ManyToMany` collection** — use `clear()` + `addAll()`, not `setCategories(new HashSet<>())` (Hibernate detaches the tracked collection).
- **Cascade DELETE on `envelope_categories`** — junction FK constraints should cascade so deleting an envelope auto-clears its links. `ON DELETE CASCADE` in migration; no need for `@OnDelete` on entity since Hibernate issues the join delete.
- **Loading `Envelope.categories` in hot paths** — use `@EntityGraph` or explicit `JOIN FETCH` when you actually need them (dialog population); default LAZY keeps list page fast.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| N:N junction table management | Custom `EnvelopeCategory` entity with `@EmbeddedId` | `@ManyToMany` with `@JoinTable` | No extra columns → simple Hibernate management suffices |
| Category tree traversal | Recursive Java method + N+1 queries | PostgreSQL `WITH RECURSIVE` CTE in one native SQL | Avoids round-trips; leverages DB strengths |
| Sign a ratio to status | Custom `if/else` enum computation in template | Server-computed `EnvelopeStatus` enum + mapping function | Single source of truth; reusable in Phase 10 dashboard |
| Money arithmetic | `BigDecimal` inline math | Existing `Money` value object (`add`, `subtract`, `zero()`) | Already validated in Phase 1; honours scale=4 and HALF_UP rounding |
| Access control | New `EnvelopeAccessRepository` | Reuse `AccountRepository.hasAccess()` | Account is the security boundary; envelope inherits (D-16) |
| Pagination for list | Server-side Pageable | Client-side slice on small lists | D-22: foyer volume low, no server pagination needed |
| Multi-select UI | Fork a second `CategoryMultiSelector` | Extend `CategorySelector` with `selectionMode` input | Consistency; avoids shared-component drift |
| Month arithmetic | `LocalDate` with day manipulation | `YearMonth` from `java.time` | Already used in `EnvelopeAllocation.getMonth()` |
| Monthly history query | 12 separate SUM queries | Single native SQL with `GROUP BY date_trunc('month', transaction_date)` | 12x round-trip reduction |

**Key insight:** The Phase 5 `TransactionService` + native SQL pattern is a working template. Copy its structure (access check → load → mutate → respond), replace the entity and aggregation query, and you have 70% of this phase. The novel work is (a) the CTE, (b) the lazy rollover formula, and (c) the multi-select frontend extension.

## Common Pitfalls

### Pitfall 1: Transaction amounts are signed — consumed convention mismatch
**What goes wrong:** `SUM(amount)` returns a negative number for spending; the envelope "budget" is positive (100€); subtracting a negative consumed INCREASES available. Tests pass; frontend shows 125% consumed for what should be 25%.
**Why it happens:** Phase 5 stores transaction amounts signed (`-45.30` for spending). Envelope logic needs absolute value.
**How to avoid:** Agree and **document in service Javadoc**: "consumed is returned as a non-negative Money; computed as `-SUM(amount)` filtered to `amount < 0`". Add a test for a refund scenario (positive amount in a spending category).
**Warning signs:** Status always GREEN regardless of spending; negative `consumedPercentage`; refund transactions visually reducing consumption (which may actually be desired, but MUST be explicit).

### Pitfall 2: PostgreSQL parameter type inference in native SQL
**What goes wrong:** `WHERE category_id IN :ids` fails at runtime with "could not determine data type of parameter" when `:ids` is empty or when bound as UUID list.
**Why it happens:** PostgreSQL can't infer types for bind parameters in certain positions — already hit in Phase 5 (see TransactionRepository native SQL with `CAST(:param AS uuid)`).
**How to avoid:** Follow the existing `TransactionRepository.findByFilters` pattern — wrap every bind parameter in `CAST(:param AS type)`. For CTE recursion base case, this is automatic because the parameter is a scalar UUID. Test with `@DataJpaTest` + real Testcontainers to catch type issues at compile/test time.
**Warning signs:** `could not determine data type` in test logs; tests passing in H2 but failing in PostgreSQL (we use real PostgreSQL via Testcontainers so this is caught).

### Pitfall 3: `@ManyToMany` collection replacement
**What goes wrong:** `envelope.setCategories(newCategories)` silently does nothing or throws `IllegalStateException` after flush.
**Why it happens:** Hibernate tracks the *original* `Set` reference. Replacing the reference detaches the managed collection; changes to the new reference aren't persisted.
**How to avoid:** When editing categories on an envelope, mutate in place:
```java
envelope.getCategories().clear();
envelope.getCategories().addAll(newCategoryEntities);
```
Never `envelope.setCategories(newSet)` after the entity is loaded.
**Warning signs:** Update request returns 200 but categories remain unchanged; test asserts categories count is wrong after save.

### Pitfall 4: Envelope `scope` derivation bypassed
**What goes wrong:** Frontend sends `scope=SHARED` on create for a PERSONAL account; backend trusts the payload; user creates a "shared" envelope on their personal account; access control breaks.
**Why it happens:** D-07 says scope is derived from `Account.accountType` — backend MUST NOT accept `scope` from the client.
**How to avoid:** `CreateEnvelopeRequest` record has NO `scope` field. Service derives: `scope = account.getAccountType() == SHARED ? EnvelopeScope.SHARED : EnvelopeScope.PERSONAL`, and `owner = scope == PERSONAL ? user : null`.
**Warning signs:** An envelope exists with `scope=SHARED` on a PERSONAL account; tests show no error because frontend always sends the "right" value.

### Pitfall 5: Category-to-envelope N:1 constraint (D-01) not enforced
**What goes wrong:** User creates envelope A linked to "Alimentation" on Account X, then later creates envelope B also linked to "Alimentation" on Account X. Transactions in "Alimentation" now impute *both* envelopes; consumed is double-counted in dashboards.
**Why it happens:** D-01 states "une catégorie ne peut être liée qu'à UNE enveloppe par compte" but requires **service-level validation** (not a unique constraint on the junction table).
**How to avoid:** In `createEnvelope` and `updateEnvelope`, validate before persist:
```java
for (UUID catId : request.categoryIds()) {
  if (envelopeRepository.existsByBankAccountIdAndCategoryId(accountId, catId)) {
    throw new DuplicateEnvelopeCategoryException("La categorie " + catId + " est deja liee a une autre enveloppe de ce compte");
  }
}
```
Need a repository method (query on junction + envelopes filtered by account). On update, exclude the envelope being edited from the check.
**Warning signs:** Dashboard shows total consumed > total spent; two envelopes report identical consumed; user confused about which envelope a transaction goes to.

### Pitfall 6: Sub-category linking loophole with D-02 (root embraces children)
**What goes wrong:** Envelope A links to ROOT category "Alimentation". Envelope B links to CHILD category "Alimentation > Courses Lidl". Which envelope takes the Lidl transaction?
**Why it happens:** D-02 says linking a root embraces its children automatically. But D-01 says a category can only be linked to ONE envelope per account — ambiguous when one envelope links to root and another to a child.
**How to avoid:** Extend the D-01 validation to check the full tree: "when linking category C to envelope E, ensure no ancestor OR descendant of C is already linked to a DIFFERENT envelope on the same account". Requires either:
- Recursive query in the existence check, OR
- Disallow linking to a child category if its root is already in any envelope on this account (simpler but restrictive).
**Recommendation:** **Disallow linking to a child if its root is linked elsewhere** (simpler, more predictable UX). Document in form help text: "Pour une couverture partielle, liez des enveloppes différentes aux sous-catégories séparément — ne mélangez pas racine et enfant." Planner should confirm with user in PLAN phase or defer as "known edge case, v2 refinement".
**Warning signs:** Test case "envelope A has root X, envelope B has child of X" passes creation but consumed aggregation is non-deterministic; user reports "où sont passées mes courses?".

### Pitfall 7: Month boundary off-by-one (timezone and day-of-month)
**What goes wrong:** A transaction dated `2026-04-30 23:50` in Europe/Paris stored as `2026-04-30` (LocalDate) gets counted in May if the query uses `CURRENT_DATE` or if YearMonth is computed UTC-ish.
**Why it happens:** `transaction_date` is a `DATE` (no time, no TZ). `YearMonth.from(LocalDate.now(ZoneId.of("Europe/Paris")))` vs `YearMonth.now()` differs if the server is UTC. Edge case at month boundaries.
**How to avoid:**
- Consumed query: use **half-open interval** `transaction_date >= monthStart AND transaction_date < nextMonthStart` (avoids `<=` last day of month ambiguity).
- Pass `YearMonth` explicitly from the client; don't compute "current month" server-side from `Clock.systemDefaultZone()`.
- In tests, use a fixed clock and dates `2026-04-01` and `2026-04-30` to cover boundaries.
**Warning signs:** Tests pass in dev (local TZ) but fail in CI (UTC); April consumed includes March 31 transactions.

### Pitfall 8: `YearMonth` JPA mapping
**What goes wrong:** `EnvelopeAllocation.month` is declared as `YearMonth` in the getter but stored as `LocalDate monthValue` in the field (see EnvelopeAllocation.java lines 33-34). Direct JPQL `WHERE ea.month = :month` will fail because Hibernate doesn't natively map `YearMonth`.
**Why it happens:** YearMonth is not a JPA persistent type out of the box.
**How to avoid:** Current entity sidesteps this by storing a `LocalDate monthValue` (day 1 of the month). Queries must use `monthValue` field with a `LocalDate.of(year, month, 1)` parameter:
```java
@Query("SELECT ea FROM EnvelopeAllocation ea WHERE ea.envelope.id = :envId AND ea.monthValue = :monthStart")
Optional<EnvelopeAllocation> findByEnvelopeIdAndMonthValue(
    @Param("envId") UUID envelopeId, @Param("monthStart") LocalDate monthStart);
```
Service converts `YearMonth → LocalDate` via `month.atDay(1)` before querying (matches the constructor pattern).
**Warning signs:** Compilation errors on JPQL; Hibernate AttributeConverter complaints.

### Pitfall 9: `DirtiesContext.AFTER_EACH_TEST_METHOD` test performance
**What goes wrong:** Each test restarts Spring context → 30-second test suite becomes 5 minutes.
**Why it happens:** The existing `TransactionControllerTest` uses `@DirtiesContext(AFTER_EACH_TEST_METHOD)` for isolation. Copying this verbatim into an `EnvelopeControllerTest` with 30+ tests is slow.
**How to avoid:** Prefer `@Transactional` rollback at the test-class level or use `@Sql` + cleanup scripts. But since the project already commits to `DirtiesContext`, follow the same pattern and accept the cost; runtime will still be acceptable (< 5 min for a foyer project).
**Warning signs:** Test suite > 10 minutes; developers skipping tests locally.

## Runtime State Inventory

Not applicable — Phase 6 is a **greenfield feature addition**, not a rename/refactor/migration. There is no existing runtime state to migrate:
- No existing envelopes in production (the app isn't deployed yet).
- No stored user data references old envelope naming.
- No external services (Plaid arrives Phase 7) hold envelope-scoped identifiers.
- No build artifacts cache envelope contracts.

The new migrations V014 and V015 will be applied fresh on first `docker compose up` post-merge. No data-migration task needed in the plan.

## Code Examples

### Example 1: Envelope entity with `@ManyToMany` + archived

```java
// Source: Adapts existing Envelope.java + Baeldung N:N pattern
@Entity
@Table(name = "envelopes")
public class Envelope {
  // ... existing fields (id, bankAccount, name, scope, owner, budget, rolloverPolicy, createdAt) ...

  @ManyToMany(fetch = FetchType.LAZY)
  @JoinTable(
      name = "envelope_categories",
      joinColumns = @JoinColumn(name = "envelope_id"),
      inverseJoinColumns = @JoinColumn(name = "category_id"))
  private Set<Category> categories = new HashSet<>();

  @Column(nullable = false)
  private boolean archived = false;

  public Set<Category> getCategories() { return categories; }
  public boolean isArchived() { return archived; }
  public void setArchived(boolean archived) { this.archived = archived; }
}
```

### Example 2: V014 migration — envelope_categories junction

```sql
-- backend/src/main/resources/db/migration/V014__create_envelope_categories.sql
CREATE TABLE envelope_categories (
    envelope_id UUID NOT NULL REFERENCES envelopes(id) ON DELETE CASCADE,
    category_id UUID NOT NULL REFERENCES categories(id) ON DELETE RESTRICT,
    PRIMARY KEY (envelope_id, category_id)
);

CREATE INDEX idx_envelope_categories_category_id ON envelope_categories(category_id);
-- envelope_id index is already covered by the PK's leading column
```

Notes:
- `ON DELETE CASCADE` on envelope_id: deleting an envelope auto-removes its links (consistent with JPA lifecycle).
- `ON DELETE RESTRICT` on category_id: cannot delete a category that's linked to any envelope (aligns with CategoryService.deleteCategory logic already blocking deletion if in use by transactions).
- No surrogate id on junction — composite PK is the natural key.

### Example 3: V015 migration — archived flag on envelopes

```sql
-- backend/src/main/resources/db/migration/V015__add_archived_to_envelopes.sql
ALTER TABLE envelopes
    ADD COLUMN archived BOOLEAN NOT NULL DEFAULT FALSE;

CREATE INDEX idx_envelopes_account_archived ON envelopes(bank_account_id, archived);
```

Mirrors `V009__add_archived_to_bank_accounts.sql` pattern.

### Example 4: Repository method for D-01 uniqueness check

```java
public interface EnvelopeRepository extends JpaRepository<Envelope, UUID> {

  /**
   * Checks whether a category is already linked to any non-archived envelope on the given account.
   * Used for D-01 validation (one category per envelope per account).
   *
   * @param envelopeIdToExclude pass null for create; pass the edited envelope's id for update
   *     to allow the category to remain on its current envelope.
   */
  @Query("""
      SELECT COUNT(e) > 0 FROM Envelope e
      JOIN e.categories c
      WHERE e.bankAccount.id = :accountId
      AND c.id = :categoryId
      AND e.archived = false
      AND (:envelopeIdToExclude IS NULL OR e.id <> :envelopeIdToExclude)
      """)
  boolean existsCategoryLinkOnAccount(
      @Param("accountId") UUID accountId,
      @Param("categoryId") UUID categoryId,
      @Param("envelopeIdToExclude") UUID envelopeIdToExclude);
}
```

### Example 5: 12-month history in a single query

```java
// Source: PostgreSQL date_trunc + month-range filter; native SQL to match aggregation in Pattern 3
@Query(value = """
    WITH months AS (
        SELECT generate_series(
            CAST(:from AS date),
            CAST(:to AS date),
            INTERVAL '1 month'
        )::date AS month_start
    ),
    envelope_cat_tree AS (
        SELECT c.id FROM envelope_categories ec
        JOIN categories c ON c.id = ec.category_id
        WHERE ec.envelope_id = CAST(:envelopeId AS uuid)
        UNION ALL
        SELECT child.id FROM categories child
        JOIN envelope_cat_tree parent ON child.parent_id = parent.id
    )
    SELECT
        m.month_start,
        COALESCE(SUM(
            CASE
                WHEN t.category_id IN (SELECT id FROM envelope_cat_tree) AND t.amount < 0 THEN -t.amount
                ELSE 0
            END
        ), 0) AS consumed_direct,
        COALESCE(SUM(
            CASE
                WHEN ts.category_id IN (SELECT id FROM envelope_cat_tree) AND ts.amount < 0 THEN -ts.amount
                ELSE 0
            END
        ), 0) AS consumed_splits
    FROM months m
    LEFT JOIN transactions t ON t.bank_account_id = CAST(:accountId AS uuid)
        AND date_trunc('month', t.transaction_date) = m.month_start
    LEFT JOIN transaction_splits ts ON ts.transaction_id = t.id
    GROUP BY m.month_start
    ORDER BY m.month_start
    """, nativeQuery = true)
List<Object[]> findMonthlyConsumptionRange(
    @Param("envelopeId") UUID envelopeId,
    @Param("accountId") UUID accountId,
    @Param("from") LocalDate from,
    @Param("to") LocalDate to);
```

The service then joins this with allocations (one additional query) and produces the `List<EnvelopeHistoryEntry>`.

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Materialized consumed column | Lazy SUM in SQL | Phase 6 D-11 | No data consistency drift; slightly slower reads at foyer scale (acceptable) |
| Batch-job rollover | Lazy formula at read | Phase 6 D-12 | Always consistent with current transaction state; no cron infra |
| Envelope = one category | Envelope = N:N categories | Phase 6 D-01 | Matches real household grouping (e.g., "Vie quotidienne" = Alimentation + Transport) |
| Cross-account envelopes (conceptual) | Per-account only | PROJECT.md v1 | Simpler mental model; deferred to v2 |
| `@SoftDelete` (Hibernate 6.4+) | Manual `archived` flag + filter | Phase 3 pattern | Explicit, queryable, aligned with existing `bank_accounts.archived` |

**Deprecated/outdated:**
- Hand-rolled rollover tables (e.g., `envelope_rollover_carry` persisted): not needed with lazy compute.
- Client-side status threshold logic duplicated across views: replaced by server-computed `EnvelopeStatus`.

## Open Questions

1. **Signed-amount convention for consumed**
   - What we know: transactions.amount is signed (`-45.30` for a spending). Phase 5 tests confirm negative for expenses.
   - What's unclear: Should refunds in a spending category reduce consumed? E.g., a `+45.30` refund on "Alimentation" — does it bring consumed down by 45.30 or is it ignored?
   - Recommendation: **Reduce consumed** (symmetric treatment, reflects real net spending). Document explicitly in service Javadoc and add a test case "refund in tracked category reduces consumed". Planner should confirm in PLAN with user.

2. **Overspend propagation to next month (CARRY_OVER)**
   - What we know: D-12 specifies the formula but treats carryOver ambiguously on negative remainders.
   - What's unclear: If month-1 overspent (consumed > budget), does the negative bleed into current month?
   - Recommendation: **Zero-clamp** (YNAB-default: overspend is realized in the month it happens; next month starts at its own budget). Tell planner to verify with user; if user wants propagation, the formula is a simple change.

3. **Root-child linking conflict (D-01 + D-02 interaction)**
   - What we know: D-01 enforces 1-category-per-envelope; D-02 says root embraces children.
   - What's unclear: If envelope A has root "Alimentation" and envelope B tries to link to child "Alimentation > Courses", is that allowed?
   - Recommendation: **Disallow** (link validation walks the tree both directions). Document in UX. Planner decides exact wording and test coverage.

4. **Chart library for history page (D-14)**
   - What we know: D-14 says "optionnel via ngx-echarts bar chart"; ngx-echarts is NOT yet in package.json.
   - What's unclear: Is "optionnel" meaning "Phase 6 can ship without it" or "add it in Phase 6 and use it"?
   - Recommendation: **Defer chart to Phase 10** (dashboard already plans to introduce ngx-echarts). In Phase 6, render history as `p-table` only — atomic decoupling. Planner should confirm; if user wants the chart now, add ngx-echarts + echarts in a dedicated plan.

5. **Allocation for future months (ENVL-02 scope)**
   - What we know: `EnvelopeAllocation` supports any `LocalDate` month. Spec says "allouer un montant mensuel" — interpretable as "default monthly" or "per-month override".
   - What's unclear: Does the user create allocations for future months in advance, or just for the current month?
   - Recommendation: Allow any month (past, current, future). Frontend dialog accepts a month picker. No restriction needed — aligned with D-08/D-10.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|-------------|-----------|---------|----------|
| PostgreSQL 17 | Backend runtime + Testcontainers tests | ✓ | 17 via docker-compose | — |
| Java 21 (Temurin) | Backend compile + run | ✓ | 21 LTS | — |
| Maven Wrapper | Backend build | ✓ | (mvnw in repo) | — |
| Node.js 22 LTS | Frontend build | ✓ | — (assumed, per CLAUDE.md stack) | — |
| pnpm | Frontend deps | ✓ | 10.32.1 (package.json) | — |
| Docker | Testcontainers | ✓ | (assumed running for CI) | — |
| `ngx-echarts` (npm) | Optional history chart | ✗ | — | Defer chart to Phase 10 (recommended) |
| `echarts` (npm) | Peer of ngx-echarts | ✗ | — | Same as above |

**Missing dependencies with no fallback:** none.

**Missing dependencies with fallback:** `ngx-echarts` + `echarts` — defer chart to Phase 10 per recommendation in Open Question 4.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | JUnit 5 + Spring Boot Test 4.0.5 + Testcontainers 2.0.0 (PostgreSQL 17) + AssertJ (backend) / Vitest 4.0.8 + Angular testing (frontend) |
| Config file | `backend/pom.xml` (Maven Surefire/Failsafe); `frontend/package.json` + Angular builder config |
| Quick run command | `./mvnw test -Dtest=EnvelopeServiceTest` (single backend test); `pnpm test --testNamePattern=envelope` (frontend) |
| Full suite command | `./mvnw verify` (all backend tests + Checkstyle + JaCoCo + dependency scan); `pnpm test` + `pnpm lint` + `pnpm format:check` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| ENVL-01 | Create envelope on account, scope derived from account type, access-controlled | integration | `./mvnw test -Dtest=EnvelopeControllerTest#create_envelope_on_personal_account_sets_scope_personal_and_owner_current_user` | ❌ Wave 0 |
| ENVL-01 | Create envelope on SHARED account sets scope=SHARED, owner=null | integration | `./mvnw test -Dtest=EnvelopeControllerTest#create_envelope_on_shared_account_sets_scope_shared_and_owner_null` | ❌ Wave 0 |
| ENVL-01 | Create without WRITE access returns 403 | integration | `./mvnw test -Dtest=EnvelopeControllerTest#create_envelope_without_write_access_returns_403` | ❌ Wave 0 |
| ENVL-01 | Create on nonexistent account returns 404 | integration | `./mvnw test -Dtest=EnvelopeControllerTest#create_envelope_on_nonexistent_account_returns_404` | ❌ Wave 0 |
| ENVL-01 | Linking a category already linked to another envelope on same account returns 409 | integration | `./mvnw test -Dtest=EnvelopeControllerTest#create_envelope_with_category_already_linked_on_account_returns_409` | ❌ Wave 0 |
| ENVL-02 | Default monthly budget applied when no allocation override exists | unit+integration | `./mvnw test -Dtest=EnvelopeServiceTest#budget_for_month_without_override_returns_envelope_default_budget` | ❌ Wave 0 |
| ENVL-02 | EnvelopeAllocation override takes precedence for specific month | integration | `./mvnw test -Dtest=EnvelopeServiceTest#budget_for_month_with_override_returns_override_amount` | ❌ Wave 0 |
| ENVL-02 | Creating overlapping allocation (same envelope + month) rejected by UNIQUE constraint | integration | `./mvnw test -Dtest=EnvelopeAllocationControllerTest#duplicate_allocation_for_same_month_returns_409` | ❌ Wave 0 |
| ENVL-03 | Transaction with category linked to envelope reduces consumed (negative amount) | integration | `./mvnw test -Dtest=EnvelopeServiceTest#consumed_sums_negative_transactions_in_linked_categories` | ❌ Wave 0 |
| ENVL-03 | Transaction splits (transaction.category null) contribute to consumed via split.category_id | integration | `./mvnw test -Dtest=EnvelopeServiceTest#consumed_includes_transaction_splits_matching_linked_categories` | ❌ Wave 0 |
| ENVL-03 | Linking root category embraces child categories (D-02) | integration | `./mvnw test -Dtest=EnvelopeServiceTest#consumed_includes_child_category_transactions_when_root_is_linked` | ❌ Wave 0 |
| ENVL-03 | Transaction in unlinked category is ignored (D-04) | integration | `./mvnw test -Dtest=EnvelopeServiceTest#transaction_in_unlinked_category_does_not_affect_consumed` | ❌ Wave 0 |
| ENVL-03 | Month boundary: transaction on last day of month counts for that month | integration | `./mvnw test -Dtest=EnvelopeServiceTest#transaction_on_last_day_of_month_included_in_that_month_consumed` | ❌ Wave 0 |
| ENVL-03 | Month boundary: transaction on first day of next month does NOT count for previous | integration | `./mvnw test -Dtest=EnvelopeServiceTest#transaction_on_first_day_of_next_month_excluded_from_previous_month_consumed` | ❌ Wave 0 |
| ENVL-04 | RESET policy: available = budget - consumed (no prev month impact) | unit | `./mvnw test -Dtest=EnvelopeServiceTest#rollover_reset_policy_ignores_previous_month` | ❌ Wave 0 |
| ENVL-04 | CARRY_OVER policy with positive remainder: carry added to this month | unit+integration | `./mvnw test -Dtest=EnvelopeServiceTest#rollover_carry_over_with_positive_previous_remainder_adds_to_available` | ❌ Wave 0 |
| ENVL-04 | CARRY_OVER policy with negative prev remainder: zero-clamped (no propagation) | unit | `./mvnw test -Dtest=EnvelopeServiceTest#rollover_carry_over_with_negative_previous_remainder_clamps_to_zero` | ❌ Wave 0 |
| ENVL-04 | CARRY_OVER lookback limited to 1 month (v1 D-12) | unit | `./mvnw test -Dtest=EnvelopeServiceTest#rollover_carry_over_lookback_limited_to_one_previous_month` | ❌ Wave 0 |
| ENVL-05 | Status GREEN when consumed < 80% of available | unit | `pnpm test --testNamePattern="status maps to GREEN"` | ❌ Wave 0 |
| ENVL-05 | Status YELLOW when consumed 80-100% | unit | `pnpm test --testNamePattern="status maps to YELLOW"` | ❌ Wave 0 |
| ENVL-05 | Status RED when consumed > 100% (overspent) | unit | `pnpm test --testNamePattern="status maps to RED"` | ❌ Wave 0 |
| ENVL-05 | Status boundary: exactly 80% is YELLOW (inclusive) | unit | `./mvnw test -Dtest=EnvelopeServiceTest#status_at_exactly_80_percent_is_yellow` | ❌ Wave 0 |
| ENVL-05 | Status boundary: exactly 100% is YELLOW (inclusive); 100.01% is RED | unit | `./mvnw test -Dtest=EnvelopeServiceTest#status_at_exactly_100_percent_is_yellow_and_above_is_red` | ❌ Wave 0 |
| ENVL-06 | History page returns 12 months of data ordered by month | integration | `./mvnw test -Dtest=EnvelopeControllerTest#get_envelope_history_returns_12_months_ordered_chronologically` | ❌ Wave 0 |
| ENVL-06 | History for month with no transactions returns 0 consumed | integration | `./mvnw test -Dtest=EnvelopeControllerTest#get_envelope_history_month_without_transactions_returns_zero_consumed` | ❌ Wave 0 |
| ENVL-07 | Update envelope with WRITE access succeeds | integration | `./mvnw test -Dtest=EnvelopeControllerTest#update_envelope_with_write_access_persists_changes` | ❌ Wave 0 |
| ENVL-07 | Update without WRITE access returns 403 | integration | `./mvnw test -Dtest=EnvelopeControllerTest#update_envelope_without_write_access_returns_403` | ❌ Wave 0 |
| ENVL-07 | Delete envelope with no allocations hard-deletes | integration | `./mvnw test -Dtest=EnvelopeControllerTest#delete_envelope_without_allocations_hard_deletes` | ❌ Wave 0 |
| ENVL-07 | Delete envelope with allocations soft-deletes (archived=true) | integration | `./mvnw test -Dtest=EnvelopeControllerTest#delete_envelope_with_allocations_soft_deletes_and_excludes_from_list` | ❌ Wave 0 |
| ENVL-07 | Archived envelope not in default list query | integration | `./mvnw test -Dtest=EnvelopeControllerTest#list_envelopes_excludes_archived_by_default` | ❌ Wave 0 |
| Frontend ENVL-01/07 | Envelope dialog create/edit form submits correctly | unit (Vitest) | `pnpm test --testNamePattern="envelope-dialog"` | ❌ Wave 0 |
| Frontend ENVL-05 | Row renders p-tag + p-progressbar with correct severity per status | unit (Vitest) | `pnpm test --testNamePattern="envelopes.*status"` | ❌ Wave 0 |
| Frontend ENVL-03 | Multi-category selector emits array of UUIDs | unit (Vitest) | `pnpm test --testNamePattern="category-selector.*multi"` | ❌ Wave 0 |
| Frontend navigation | Sidebar shows Enveloppes link; /envelopes route loads | unit (Vitest) | `pnpm test --testNamePattern="sidebar.*envelopes"` | ❌ Wave 0 |

### Boundary Cases (explicit coverage)

| Boundary | Test Scenario |
|----------|---------------|
| Zero budget | Envelope with budget=0, status should be GREEN (no division by zero) |
| Zero consumed | Envelope with consumed=0, status GREEN, percentage=0 |
| First day of month (2026-04-01) | Transaction counts for April |
| Last day of month (2026-04-30) | Transaction counts for April, not May |
| First day of next month (2026-05-01) | Transaction does NOT count for April |
| Month = January (rollover from December previous year) | Year boundary handled correctly |
| Status = exactly 80% | YELLOW (inclusive per D-13 "80-100%") |
| Status = exactly 100% | YELLOW (inclusive upper bound) |
| Status = 100.01% | RED |
| Consumed > budget (overspent by large amount) | Status RED, percentage capped at 100 for progress bar display but real value available |
| Envelope with 0 categories linked | consumed = 0 always (vacuous sum) |
| Root category linked with no children | only root transactions counted (no recursion hit) |
| Root linked + deeply categorized child has own transactions | child transactions counted (CTE finds them) |
| Concurrent user updates | Optimistic locking not strictly needed at foyer scale; last-write-wins is acceptable (document this decision in PLAN) |
| User without WRITE attempts mutation | 403 |
| User without READ attempts read | 403 |
| Nonexistent envelope id | 404 |
| Nonexistent account id on create | 404 |
| Category linked to another envelope on same account | 409 Conflict (D-01) |
| Same category on two envelopes on DIFFERENT accounts | ALLOWED (D-01 is "per account") |

### Property-Based Testing Candidates (jqwik optional)

> Not currently in pom.xml. Can be added as Apache 2.0 dep (`net.jqwik:jqwik:1.9.x`) if deemed useful. Recommendation: **skip for Phase 6, use explicit parameterized tests instead** — property-based testing shines for pure math, and rollover formula is simple enough that boundary-value analysis via `@ParameterizedTest` covers it well. If jqwik is added, good candidates would be:

- **Rollover commutativity:** `computeAvailable(e, m)` = `budget(m) + rollover_contribution(m-1) - consumed(m)` across arbitrary months and policies.
- **Status monotonicity:** increasing `consumed` monotonically moves `EnvelopeStatus` GREEN→YELLOW→RED.
- **CTE completeness:** for any category tree (depth ≤ 2), the recursive CTE returns exactly {root} ∪ children(root) for a root-linked envelope.
- **Aggregation associativity:** sum of per-month consumed over 12 months = sum of all transactions in envelope's categories over that year.

### Sampling Rate

- **Per task commit:** `./mvnw test -Dtest=EnvelopeServiceTest -Dtest=EnvelopeControllerTest` (envelope package only — ~30s with Testcontainers reuse)
- **Per wave merge:** `./mvnw verify` (full backend suite + Checkstyle + JaCoCo threshold check + OWASP scan) + `pnpm test && pnpm lint && pnpm format:check`
- **Phase gate:** Full suite green + manual smoke (create envelope, spend money via test transaction, verify consumed updates, toggle rollover, verify status badge color) before `/gsd:verify-work`

### Wave 0 Gaps

All test files are new to this phase. Wave 0 should scaffold:

- [ ] `backend/src/test/java/com/prosperity/envelope/EnvelopeControllerTest.java` — integration tests (Testcontainers, MockMvc) covering ENVL-01, ENVL-02, ENVL-06, ENVL-07 and access control variants
- [ ] `backend/src/test/java/com/prosperity/envelope/EnvelopeServiceTest.java` — unit/integration for consumed aggregation, rollover formula, status thresholds (ENVL-03, ENVL-04, ENVL-05 business logic)
- [ ] `backend/src/test/java/com/prosperity/envelope/EnvelopeAllocationControllerTest.java` — monthly override endpoints
- [ ] `backend/src/test/java/com/prosperity/envelope/EnvelopeTest.java` — **already exists** (rollover/overspent unit). Can be extended if additional domain behavior is added to `Envelope.java`.
- [ ] `frontend/src/app/envelopes/envelopes.spec.ts` — list page, filter by account, status rendering
- [ ] `frontend/src/app/envelopes/envelope-dialog.spec.ts` — create/edit form, multi-select categories
- [ ] `frontend/src/app/envelopes/envelope-details.spec.ts` — history page, 12-month table
- [ ] `frontend/src/app/envelopes/envelope.service.spec.ts` — HttpClient interactions, signals
- [ ] `frontend/src/app/shared/category-selector.spec.ts` — **already exists**; extend to cover new multi-select mode
- [ ] `frontend/src/app/layout/sidebar.spec.ts` — **already exists**; extend to assert Enveloppes link

**No framework install needed** — JUnit 5, Testcontainers 2.0.0, AssertJ, MockMvc, and Vitest are all present. ArchUnit 1.3.0 is also available if the planner wants to add a package-layering rule (e.g., "envelope.* may not import transaction.* directly, only through Repository interfaces").

## Sources

### Primary (HIGH confidence)
- `CLAUDE.md` (project root) — stack versions, constraints, testing rules — read directly
- `.planning/PROJECT.md` — Key Decision "Enveloppes par compte (pas transversales)"
- `.planning/REQUIREMENTS.md` §Budgets Enveloppes — ENVL-01 à ENVL-07
- `.planning/phases/06-envelope-budgets/06-CONTEXT.md` — 22 locked decisions (D-01 to D-22)
- `.planning/STATE.md` — blocker resolution ("Envelope shared visibility") now locked by D-05
- `docs/adr/0002-architecture-layered.md` — package-by-feature + strategic abstraction (only connector)
- `backend/src/main/java/com/prosperity/envelope/Envelope.java` — existing entity (id, bankAccount, name, scope, owner, budget, rolloverPolicy, createdAt)
- `backend/src/main/java/com/prosperity/envelope/EnvelopeAllocation.java` — existing entity (envelope, monthValue LocalDate, allocatedAmount)
- `backend/src/main/java/com/prosperity/transaction/TransactionService.java` — canonical 403 vs 404 pattern, access-check helper
- `backend/src/main/java/com/prosperity/transaction/TransactionRepository.java` — canonical native SQL + `CAST(:param AS type)` pattern
- `backend/src/main/java/com/prosperity/account/AccountRepository.java` — canonical access-filtered JPQL
- `backend/src/main/java/com/prosperity/category/CategoryService.java` — category hierarchy conventions (max 2 levels)
- `backend/src/main/resources/db/migration/V006__create_envelopes.sql` — envelopes + envelope_allocations schema
- `backend/src/main/resources/db/migration/V007__migrate_money_columns_to_numeric.sql` — NUMERIC(19,4) Money storage
- `backend/src/main/resources/db/migration/V009__add_archived_to_bank_accounts.sql` (referenced via STATE.md) — soft delete pattern template
- `frontend/src/app/shared/category-selector.ts` — existing single-select component (use `p-treeSelect` tree)
- `frontend/src/app/transactions/transactions.ts` — p-table + p-treeSelect filter pattern
- `backend/src/test/java/com/prosperity/transaction/TransactionControllerTest.java` — Testcontainers + MockMvc pattern
- `backend/src/test/java/com/prosperity/envelope/EnvelopeTest.java` — existing unit tests for rollover/overspent
- [PostgreSQL 18 WITH Queries (CTE) docs](https://www.postgresql.org/docs/current/queries-with.html) — recursive CTE syntax, performance guidance (HIGH)
- [PrimeNG TreeSelect](https://primeng.org/treeselect) — `selectionMode="checkbox"` and multi-select behavior (HIGH)
- [PrimeNG ProgressBar](https://primeng.org/progressbar) — value 0-100, determinate mode, styleClass override (HIGH)
- [PrimeNG Tag](https://primeng.org/tag) — severity=success/info/warn/danger mapping (HIGH)

### Secondary (MEDIUM confidence)
- [Baeldung — Many-To-Many Relationship in JPA](https://www.baeldung.com/jpa-many-to-many) — `@ManyToMany` + `@JoinTable` pattern (MEDIUM — matches existing Hibernate 7 convention, no API changes in Boot 4)
- [Vlad Mihalcea — best way to map many-to-many with extra columns](https://vladmihalcea.com/the-best-way-to-map-a-many-to-many-association-with-extra-columns-when-using-jpa-and-hibernate/) — confirms that simple N:N (no extra columns) does NOT need an intermediate entity (MEDIUM)
- [Cybertec — PostgreSQL speeding up recursive queries and hierarchic data](https://www.cybertec-postgresql.com/en/postgresql-speeding-up-recursive-queries-and-hierarchic-data/) — index on parent_id, UNION ALL over UNION (MEDIUM)
- [Baeldung — Customizing JPA queries with aggregation](https://www.baeldung.com/jpa-queries-custom-result-with-aggregation-functions) — constructor expressions, SUM patterns (MEDIUM)
- [YNAB — Master Your Monthly Rollovers](https://www.ynab.com/blog/master-your-monthly-rollovers) — rollover UX conventions, zero-clamping on overspend (MEDIUM — informs Open Question 2)
- [YNAB — When the Month Rolls Over: A Guide](https://support.ynab.com/en_us/when-the-month-rolls-over-a-guide-rkyyd6qC9) — rollover user mental model (MEDIUM)

### Tertiary (LOW confidence — flagged for validation)
- [GeeksforGeeks — Angular PrimeNG Form TreeSelect Multiple Component](https://www.geeksforgeeks.org/angular-primeng-form-treeselect-multiple-component/) — content referenced but superseded by official docs (LOW, cross-check with primeng.org/treeselect which is HIGH)
- [Mastering-postgres — Hierarchical recursive CTE](https://masteringpostgres.com/watch/recursive-hierarchy) — third-party tutorial supporting CTE approach (LOW)

## Metadata

**Confidence breakdown:**
- **Standard stack:** HIGH — all libraries confirmed from pom.xml/package.json and recent CLAUDE.md stack rules; no new libs needed for v1 scope.
- **Architecture:** HIGH — pattern is a direct lift from TransactionService + AccountService; only novel piece is the recursive CTE, confirmed against PostgreSQL docs.
- **N:N modeling:** HIGH — simple `@ManyToMany` + composite-PK junction is the idiomatic Hibernate solution for no-extra-column joins.
- **Consumed aggregation:** HIGH — native SQL is the only viable path given JPQL's lack of recursive CTE support; the pattern matches Phase 5 precedent.
- **Rollover formula:** HIGH — pure function of 4 queries; boundary cases covered.
- **Status thresholds & UI mapping:** HIGH — PrimeNG docs confirm severity values and templating.
- **Frontend multi-select:** HIGH — `p-treeSelect` multi is native in PrimeNG 21 (already used elsewhere in single mode).
- **Pitfalls:** MEDIUM-HIGH — most drawn from existing code comments (MoneyConverter, HttpParams workaround, CAST pattern, YearMonth storage); the D-01/D-02 interaction (Pitfall 6) is inferred from decisions, needs planner confirmation.
- **Validation/tests:** HIGH — Testcontainers pattern is well established; boundary cases are explicit.

**Research date:** 2026-04-22
**Valid until:** 2026-05-22 (30 days — stable ecosystem, no incoming major releases of Spring Boot 4, PrimeNG 21, or PostgreSQL 17 expected in window)

---

*Research complete — planner can consume this file to produce atomic PLAN.md entries.*
