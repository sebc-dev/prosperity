---
phase: 06-envelope-budgets
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - backend/src/main/resources/db/migration/V014__create_envelope_categories.sql
  - backend/src/main/resources/db/migration/V015__add_archived_to_envelopes.sql
  - backend/src/main/java/com/prosperity/envelope/Envelope.java
  - backend/src/main/java/com/prosperity/envelope/EnvelopeRepository.java
  - backend/src/main/java/com/prosperity/envelope/EnvelopeAllocationRepository.java
autonomous: true
requirements:
  - ENVL-01
  - ENVL-02
  - ENVL-03
  - ENVL-07
must_haves:
  truths:
    - "Database has envelope_categories junction table linking envelopes to categories (N:N)"
    - "Envelopes table has archived BOOLEAN NOT NULL DEFAULT FALSE column"
    - "Envelope JPA entity exposes Set<Category> categories via @ManyToMany and an archived flag"
    - "EnvelopeRepository can return non-archived envelopes accessible to a user (account-filtered, JPQL JOIN AccountAccess)"
    - "EnvelopeRepository.existsCategoryLinkOnAccount enforces D-01 (one category per envelope per account)"
    - "EnvelopeRepository can aggregate consumed for one envelope+month using a recursive CTE over envelope_categories + categories.parent_id, summing transactions.amount AND transaction_splits.amount where amount < 0; transactions with non-null category_id AND child splits are counted only via the splits branch (defensive de-duplication for Phase 5 D-06 convention)"
    - "EnvelopeRepository can return 12-month consumption history in a single native query (same de-duplication rule applies)"
    - "EnvelopeAllocationRepository can lookup an override by (envelopeId, monthStart) and list overrides for an envelope"
  artifacts:
    - path: "backend/src/main/resources/db/migration/V014__create_envelope_categories.sql"
      provides: "envelope_categories junction table (D-01)"
      contains: "CREATE TABLE envelope_categories"
    - path: "backend/src/main/resources/db/migration/V015__add_archived_to_envelopes.sql"
      provides: "soft-delete archived flag on envelopes (D-18)"
      contains: "ALTER TABLE envelopes"
    - path: "backend/src/main/java/com/prosperity/envelope/Envelope.java"
      provides: "Enriched Envelope entity with @ManyToMany Set<Category> categories + archived"
      contains: "private Set<Category> categories"
    - path: "backend/src/main/java/com/prosperity/envelope/EnvelopeRepository.java"
      provides: "Access-filtered queries, D-01 uniqueness check, consumed aggregation (split-dedup), monthly history"
      contains: "existsCategoryLinkOnAccount"
    - path: "backend/src/main/java/com/prosperity/envelope/EnvelopeAllocationRepository.java"
      provides: "findByEnvelopeIdAndMonthValue + findByEnvelopeIdAndMonthValueBetween"
      contains: "findByEnvelopeIdAndMonthValue"
  key_links:
    - from: "Envelope.java"
      to: "envelope_categories table"
      via: "@JoinTable(name = \"envelope_categories\")"
      pattern: "@JoinTable\\(\\s*name = \"envelope_categories\""
    - from: "EnvelopeRepository.java"
      to: "AccountAccess (access control inheritance)"
      via: "JPQL JOIN AccountAccess aa ON aa.bankAccount = ba"
      pattern: "JOIN AccountAccess"
    - from: "EnvelopeRepository consumed query"
      to: "transactions + transaction_splits"
      via: "Native SQL UNION ALL inside recursive CTE with NOT EXISTS dedup on transactions branch"
      pattern: "WITH RECURSIVE envelope_cat_tree"
---

<objective>
Build the persistence foundation for Phase 6 envelope budgets:
- Add a `envelope_categories` N:N junction table (D-01) and an `archived` flag on `envelopes` (D-18) via Flyway V014 + V015 migrations.
- Enrich the existing `Envelope` JPA entity with the `@ManyToMany Set<Category> categories` relation and the `archived` boolean.
- Enrich the empty `EnvelopeRepository` with: access-filtered list queries (filtering through `AccountAccess` exactly like Phase 5), the D-01 uniqueness check (`existsCategoryLinkOnAccount`), the consumed aggregation native SQL with a PostgreSQL recursive CTE (with NOT EXISTS dedup so split parents are counted only via the splits branch), and a single-query 12-month consumption history.
- Enrich the empty `EnvelopeAllocationRepository` with month lookup queries.

Purpose: Phase 6 service layer (Plan 04) and controller (Plan 05) cannot begin until this data layer is in place. This plan is dependency-free and runs in Wave 1.

Output: V014 + V015 migrations applied successfully; Envelope entity ManyToMany relation persisted; repository queries compilable and structure-tested via standard Spring Data startup.
</objective>

<execution_context>
@/home/negus/dev/prosperity/.claude/get-shit-done/workflows/execute-plan.md
@/home/negus/dev/prosperity/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT.md
@.planning/ROADMAP.md
@.planning/STATE.md
@.planning/phases/06-envelope-budgets/06-CONTEXT.md
@.planning/phases/06-envelope-budgets/06-RESEARCH.md

@backend/src/main/java/com/prosperity/envelope/Envelope.java
@backend/src/main/java/com/prosperity/envelope/EnvelopeAllocation.java
@backend/src/main/java/com/prosperity/envelope/EnvelopeRepository.java
@backend/src/main/java/com/prosperity/envelope/EnvelopeAllocationRepository.java
@backend/src/main/java/com/prosperity/category/Category.java
@backend/src/main/java/com/prosperity/account/AccountAccess.java
@backend/src/main/java/com/prosperity/account/AccountRepository.java
@backend/src/main/java/com/prosperity/transaction/TransactionRepository.java
@backend/src/main/resources/db/migration/V006__create_envelopes.sql
@backend/src/main/resources/db/migration/V009__add_archived_to_bank_accounts.sql
@backend/src/main/resources/db/migration/V012__create_transaction_splits.sql

<revision_note>
**Iteration 1 revision:** Native SQL consumed query updated to add `AND NOT EXISTS (SELECT 1 FROM transaction_splits ts2 WHERE ts2.transaction_id = t.id)` to the transactions branch of the UNION ALL (BLOCKER 2). Phase 5 D-06 convention says split-parent transactions should have `category_id = NULL`, but defending against future drift (e.g., import code that leaves both populated) prevents silent double-counting in dashboards. Same dedup applied to monthly_direct in the 12-month history query.
</revision_note>

<interfaces>
<!-- Existing types the executor needs to work against. Do NOT explore further. -->

Money value object (com.prosperity.shared.Money):
```java
public record Money(BigDecimal amount) {
  public static Money of(String value);   // factory (BigDecimal scale 4, HALF_UP)
  public static Money zero();
  public Money add(Money other);
  public Money subtract(Money other);
}
```
MoneyConverter is the JPA AttributeConverter (already present, used by Envelope.budget).

Existing Envelope entity fields (KEEP these — only add categories + archived):
- UUID id (GeneratedValue UUID)
- @ManyToOne Account bankAccount (joinColumn bank_account_id)
- String name (length 100)
- @Enumerated EnvelopeScope scope (length 20)
- @ManyToOne User owner (joinColumn owner_id, nullable)
- @Convert(MoneyConverter) Money budget (NUMERIC(19,4))
- @Enumerated RolloverPolicy rolloverPolicy (length 20, default RESET)
- Instant createdAt (TIMESTAMPTZ)

Existing helper methods to preserve: isOverspent(Money consumed), rollover(Money remaining), constructors, getters/setters.

Existing EnvelopeAllocation entity (UNCHANGED in this plan):
- @ManyToOne Envelope envelope (joinColumn envelope_id)
- LocalDate monthValue (column "month")  -- this is the day-1 of the month
- @Convert(MoneyConverter) Money allocatedAmount (NUMERIC(19,4))
- getMonth()/setMonth() converts to/from YearMonth via monthValue
- Composite-uniqueness already enforced in V006: UNIQUE(envelope_id, month)

Category entity (referenced via N:N) lives at com.prosperity.category.Category — has UUID id and @ManyToOne Category parent.

AccountAccess entity (used in JPQL JOIN) lives at com.prosperity.account.AccountAccess — fields: User user, Account bankAccount, AccessLevel accessLevel.

TransactionRepository.findByFilters proves the native-SQL + CAST(:param AS uuid) pattern that this plan must mirror for the consumed query.

transaction_splits table (V012): columns id, transaction_id, category_id, amount. Phase 5 D-06: when a transaction is split, the parent transaction's category_id is set to NULL and the splits carry the per-line categories. This plan defends against drift via NOT EXISTS dedup (see Task 3).
</interfaces>
</context>

<tasks>

<task type="auto" tdd="false">
  <name>Task 1: V014 + V015 Flyway migrations (envelope_categories junction + archived flag)</name>
  <files>backend/src/main/resources/db/migration/V014__create_envelope_categories.sql, backend/src/main/resources/db/migration/V015__add_archived_to_envelopes.sql</files>
  <read_first>
    - backend/src/main/resources/db/migration/V006__create_envelopes.sql (existing envelopes + envelope_allocations schema; confirm column names + types)
    - backend/src/main/resources/db/migration/V009__add_archived_to_bank_accounts.sql (template for archived flag pattern)
    - backend/src/main/resources/db/migration/V012__create_transaction_splits.sql (latest reference for native SQL style and ON DELETE CASCADE)
    - backend/src/main/resources/db/migration/V004__create_categories.sql (confirm categories.id type and parent_id column)
  </read_first>
  <action>
Create two new Flyway migrations using the EXACT SQL below.

**File 1: `backend/src/main/resources/db/migration/V014__create_envelope_categories.sql`**

```sql
CREATE TABLE envelope_categories (
    envelope_id UUID NOT NULL REFERENCES envelopes(id) ON DELETE CASCADE,
    category_id UUID NOT NULL REFERENCES categories(id) ON DELETE RESTRICT,
    PRIMARY KEY (envelope_id, category_id)
);

CREATE INDEX idx_envelope_categories_category_id ON envelope_categories(category_id);
```

Notes:
- `ON DELETE CASCADE` on envelope_id: deleting an envelope auto-clears its links.
- `ON DELETE RESTRICT` on category_id: cannot delete a category linked to any envelope (mirrors CategoryService policy).
- No surrogate id; composite PK is the natural key (D-01).
- The PK's leading column already indexes envelope_id; only category_id needs an explicit index.

**File 2: `backend/src/main/resources/db/migration/V015__add_archived_to_envelopes.sql`**

```sql
ALTER TABLE envelopes
    ADD COLUMN archived BOOLEAN NOT NULL DEFAULT FALSE;

CREATE INDEX idx_envelopes_account_archived ON envelopes(bank_account_id, archived);
```

Notes:
- Mirrors V009__add_archived_to_bank_accounts.sql pattern but adds the composite index for the access-filtered list query that filters by both bank_account_id and archived.
- `DEFAULT FALSE` so existing rows (none yet, but defensive) become non-archived.

Do NOT modify V006 or any earlier migration. Do NOT add a new id column to the junction.
  </action>
  <verify>
    <automated>cd /home/negus/dev/prosperity && ./mvnw -pl backend test -Dtest=ProsperityApplicationTest -q 2>&1 | tail -20</automated>
  </verify>
  <acceptance_criteria>
    - File `backend/src/main/resources/db/migration/V014__create_envelope_categories.sql` exists
    - File `backend/src/main/resources/db/migration/V015__add_archived_to_envelopes.sql` exists
    - `grep -c "CREATE TABLE envelope_categories" backend/src/main/resources/db/migration/V014__create_envelope_categories.sql` returns 1
    - `grep -c "ON DELETE CASCADE" backend/src/main/resources/db/migration/V014__create_envelope_categories.sql` returns 1
    - `grep -c "ON DELETE RESTRICT" backend/src/main/resources/db/migration/V014__create_envelope_categories.sql` returns 1
    - `grep -c "PRIMARY KEY (envelope_id, category_id)" backend/src/main/resources/db/migration/V014__create_envelope_categories.sql` returns 1
    - `grep -c "CREATE INDEX idx_envelope_categories_category_id" backend/src/main/resources/db/migration/V014__create_envelope_categories.sql` returns 1
    - `grep -c "ADD COLUMN archived BOOLEAN NOT NULL DEFAULT FALSE" backend/src/main/resources/db/migration/V015__add_archived_to_envelopes.sql` returns 1
    - `grep -c "CREATE INDEX idx_envelopes_account_archived" backend/src/main/resources/db/migration/V015__add_archived_to_envelopes.sql` returns 1
    - ProsperityApplicationTest exits 0 (Flyway applies V014 + V015 cleanly to Testcontainers PostgreSQL during context startup)
  </acceptance_criteria>
  <done>Both migrations created with exact schema above; ProsperityApplicationTest passes confirming Flyway applies them on Testcontainers PostgreSQL without error.</done>
</task>

<task type="auto" tdd="false">
  <name>Task 2: Enrich Envelope entity (categories ManyToMany + archived flag)</name>
  <files>backend/src/main/java/com/prosperity/envelope/Envelope.java</files>
  <read_first>
    - backend/src/main/java/com/prosperity/envelope/Envelope.java (current state — preserve all existing fields, constructors, helper methods)
    - backend/src/main/java/com/prosperity/category/Category.java (confirm package + class signature for the @ManyToMany target)
  </read_first>
  <action>
Modify `backend/src/main/java/com/prosperity/envelope/Envelope.java` by adding the two new fields exactly as below. Do NOT remove or rename any existing field, constructor, getter, setter, or helper method (`isOverspent`, `rollover`).

**Imports to add** (alongside existing imports):
```java
import com.prosperity.category.Category;
import jakarta.persistence.JoinTable;
import jakarta.persistence.ManyToMany;
import java.util.HashSet;
import java.util.Set;
```

**New fields** (insert after the `rolloverPolicy` field, before `createdAt`):

```java
  @ManyToMany(fetch = FetchType.LAZY)
  @JoinTable(
      name = "envelope_categories",
      joinColumns = @JoinColumn(name = "envelope_id"),
      inverseJoinColumns = @JoinColumn(name = "category_id"))
  private Set<Category> categories = new HashSet<>();

  @Column(nullable = false)
  private boolean archived = false;
```

**New accessors** (append at the end of the class, after `setCreatedAt`):

```java
  public Set<Category> getCategories() {
    return categories;
  }

  public void setCategories(Set<Category> categories) {
    this.categories = categories;
  }

  public boolean isArchived() {
    return archived;
  }

  public void setArchived(boolean archived) {
    this.archived = archived;
  }
```

**Important pitfall (Pitfall 3 in RESEARCH.md):** Even though we expose `setCategories`, the service in Plan 04 will mutate the set in place via `clear() + addAll()` for updates. Do NOT add any `equals/hashCode` on Envelope (Hibernate/JPA best practice — entities use id equality only, but since we use UUID generated by JPA we keep default Object identity).

Do NOT add Lombok. Do NOT change the `@Entity`/`@Table` annotations. Keep `Envelope` as a regular class (not record).
  </action>
  <verify>
    <automated>cd /home/negus/dev/prosperity && ./mvnw -pl backend compile -q 2>&1 | tail -10</automated>
  </verify>
  <acceptance_criteria>
    - `grep -c "import com.prosperity.category.Category;" backend/src/main/java/com/prosperity/envelope/Envelope.java` returns 1
    - `grep -c "@ManyToMany(fetch = FetchType.LAZY)" backend/src/main/java/com/prosperity/envelope/Envelope.java` returns 1
    - `grep -c "private Set<Category> categories = new HashSet<>();" backend/src/main/java/com/prosperity/envelope/Envelope.java` returns 1
    - `grep -c "private boolean archived = false;" backend/src/main/java/com/prosperity/envelope/Envelope.java` returns 1
    - `grep -c "public Set<Category> getCategories()" backend/src/main/java/com/prosperity/envelope/Envelope.java` returns 1
    - `grep -c "public boolean isArchived()" backend/src/main/java/com/prosperity/envelope/Envelope.java` returns 1
    - `grep -c "public boolean isOverspent" backend/src/main/java/com/prosperity/envelope/Envelope.java` returns 1 (preserved)
    - `grep -c "public Money rollover" backend/src/main/java/com/prosperity/envelope/Envelope.java` returns 1 (preserved)
    - `./mvnw -pl backend compile -q` exits 0
  </acceptance_criteria>
  <done>Envelope entity compiles, exposes Set<Category> categories via @ManyToMany with envelope_categories join table, exposes archived boolean; all existing fields/methods preserved.</done>
</task>

<task type="auto" tdd="false">
  <name>Task 3: Enrich EnvelopeRepository (access-filtered list, D-01 uniqueness, consumed CTE with split dedup, 12-month history)</name>
  <files>backend/src/main/java/com/prosperity/envelope/EnvelopeRepository.java</files>
  <read_first>
    - backend/src/main/java/com/prosperity/envelope/EnvelopeRepository.java (current empty state)
    - backend/src/main/java/com/prosperity/account/AccountRepository.java (canonical access-filtered JPQL pattern with JOIN AccountAccess)
    - backend/src/main/java/com/prosperity/transaction/TransactionRepository.java (canonical native SQL + CAST(:param AS uuid) pattern)
    - backend/src/main/java/com/prosperity/account/AccountAccess.java (confirm field names: bankAccount, user.id, accessLevel)
    - backend/src/main/resources/db/migration/V012__create_transaction_splits.sql (confirm transaction_splits column names: transaction_id, category_id, amount; this is the table we dedup against)
    - backend/src/main/resources/db/migration/V005__create_transactions.sql (confirm transactions column names: bank_account_id, category_id, transaction_date, amount)
  </read_first>
  <behavior>
    - Defensive de-duplication on the consumed CTE: transactions whose `id` appears as a `transaction_id` in `transaction_splits` are excluded from the transactions branch of the UNION ALL — they are counted via the splits branch only. Phase 5 D-06 says split parents have `category_id = NULL` (so they wouldn't match `t.category_id IN (...)` anyway), but the NOT EXISTS clause makes this guarantee independent of the convention.
  </behavior>
  <action>
Replace the contents of `backend/src/main/java/com/prosperity/envelope/EnvelopeRepository.java` with the following complete file. The package and `JpaRepository<Envelope, UUID>` extension stay; everything else is added.

```java
package com.prosperity.envelope;

import java.math.BigDecimal;
import java.time.LocalDate;
import java.util.List;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

/**
 * Spring Data JPA repository for Envelope entities. All listing queries filter by user access
 * inherited from the account (D-16) and exclude archived envelopes by default (D-18).
 */
public interface EnvelopeRepository extends JpaRepository<Envelope, UUID> {

  /**
   * Returns non-archived envelopes for a single account, accessible to the user.
   * Used by GET /api/accounts/{accountId}/envelopes.
   */
  @Query("""
      SELECT DISTINCT e FROM Envelope e
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

  /**
   * Returns all non-archived envelopes accessible to the user across every account they have
   * access to. Used by GET /api/envelopes (no accountId filter).
   */
  @Query("""
      SELECT DISTINCT e FROM Envelope e
      JOIN e.bankAccount ba
      JOIN AccountAccess aa ON aa.bankAccount = ba
      WHERE aa.user.id = :userId
      AND e.archived = false
      AND ba.archived = false
      ORDER BY ba.name ASC, e.name ASC
      """)
  List<Envelope> findAllAccessibleToUser(@Param("userId") UUID userId);

  /**
   * Returns ALL envelopes (including archived) accessible to the user, optionally filtered by
   * account. Used when the list page query parameter includeArchived=true is set.
   */
  @Query("""
      SELECT DISTINCT e FROM Envelope e
      JOIN e.bankAccount ba
      JOIN AccountAccess aa ON aa.bankAccount = ba
      WHERE aa.user.id = :userId
      AND ba.archived = false
      ORDER BY ba.name ASC, e.name ASC
      """)
  List<Envelope> findAllAccessibleToUserIncludingArchived(@Param("userId") UUID userId);

  /**
   * D-01 enforcement: returns true if the given category is already linked to any non-archived
   * envelope on the given account. When updating an envelope, pass envelopeIdToExclude=its id so
   * the category is allowed to remain on the envelope being edited; pass null on create.
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

  /**
   * Aggregates the consumed amount for an envelope on a single month. Uses a recursive CTE to
   * expand each linked category root to root + descendants (D-02), then sums absolute values of
   * negative amounts from BOTH transactions.amount (when not split) AND transaction_splits.amount
   * (D-03). Half-open month interval [monthStart, nextMonthStart) avoids boundary off-by-one
   * (Pitfall 7). Returns 0 when no matching transactions exist.
   *
   * <p><b>Split de-duplication (defensive):</b> the transactions branch of the UNION ALL excludes
   * any transaction that has at least one row in transaction_splits — those are aggregated via
   * the splits branch only. Phase 5 D-06 says split parents have {@code category_id = NULL} so
   * they wouldn't match the IN clause anyway, but the NOT EXISTS guard makes the dedup independent
   * of that convention (defensive against future import code that leaves both populated).
   *
   * <p>Convention: consumed is returned as a NON-NEGATIVE BigDecimal (we negate the negative
   * amounts). A refund (positive amount) in a tracked category REDUCES consumed because we treat
   * positive amounts symmetrically via -t.amount when t.amount &gt; 0 in the negation step. To
   * keep semantics simple, this query SUMS only negative amounts and negates them — refunds are
   * documented as out of v1 scope (Open Question 1 in RESEARCH.md, planner default = filter
   * spending only).
   */
  @Query(value = """
      WITH RECURSIVE envelope_cat_tree AS (
          SELECT c.id
          FROM envelope_categories ec
          JOIN categories c ON c.id = ec.category_id
          WHERE ec.envelope_id = CAST(:envelopeId AS uuid)
          UNION ALL
          SELECT child.id
          FROM categories child
          JOIN envelope_cat_tree parent ON child.parent_id = parent.id
      )
      SELECT COALESCE(SUM(spent.amount), 0) AS consumed
      FROM (
          SELECT -t.amount AS amount
          FROM transactions t
          WHERE t.bank_account_id = CAST(:accountId AS uuid)
            AND t.category_id IN (SELECT id FROM envelope_cat_tree)
            AND t.amount < 0
            AND t.transaction_date >= CAST(:monthStart AS date)
            AND t.transaction_date < CAST(:nextMonthStart AS date)
            AND NOT EXISTS (
                SELECT 1 FROM transaction_splits ts2
                WHERE ts2.transaction_id = t.id
            )
          UNION ALL
          SELECT -ts.amount AS amount
          FROM transaction_splits ts
          JOIN transactions t ON t.id = ts.transaction_id
          WHERE t.bank_account_id = CAST(:accountId AS uuid)
            AND ts.category_id IN (SELECT id FROM envelope_cat_tree)
            AND ts.amount < 0
            AND t.transaction_date >= CAST(:monthStart AS date)
            AND t.transaction_date < CAST(:nextMonthStart AS date)
      ) spent
      """, nativeQuery = true)
  BigDecimal sumConsumedForMonth(
      @Param("envelopeId") UUID envelopeId,
      @Param("accountId") UUID accountId,
      @Param("monthStart") LocalDate monthStart,
      @Param("nextMonthStart") LocalDate nextMonthStart);

  /**
   * Returns 12 month-buckets of consumption between [from, to). Each row: [month_start (date),
   * consumed (numeric)]. Months without transactions in linked categories return consumed = 0
   * (LEFT JOIN preserves the bucket from generate_series). Used for the Envelope Details page
   * 12-month history table (ENVL-06). Same NOT EXISTS dedup as sumConsumedForMonth (split parents
   * counted only via the splits branch).
   */
  @Query(value = """
      WITH RECURSIVE envelope_cat_tree AS (
          SELECT c.id
          FROM envelope_categories ec
          JOIN categories c ON c.id = ec.category_id
          WHERE ec.envelope_id = CAST(:envelopeId AS uuid)
          UNION ALL
          SELECT child.id
          FROM categories child
          JOIN envelope_cat_tree parent ON child.parent_id = parent.id
      ),
      months AS (
          SELECT generate_series(
              CAST(:from AS date),
              CAST(:to AS date) - INTERVAL '1 day',
              INTERVAL '1 month'
          )::date AS month_start
      ),
      monthly_direct AS (
          SELECT date_trunc('month', t.transaction_date)::date AS month_start,
                 SUM(-t.amount) AS consumed
          FROM transactions t
          WHERE t.bank_account_id = CAST(:accountId AS uuid)
            AND t.category_id IN (SELECT id FROM envelope_cat_tree)
            AND t.amount < 0
            AND t.transaction_date >= CAST(:from AS date)
            AND t.transaction_date < CAST(:to AS date)
            AND NOT EXISTS (
                SELECT 1 FROM transaction_splits ts2
                WHERE ts2.transaction_id = t.id
            )
          GROUP BY date_trunc('month', t.transaction_date)
      ),
      monthly_splits AS (
          SELECT date_trunc('month', t.transaction_date)::date AS month_start,
                 SUM(-ts.amount) AS consumed
          FROM transaction_splits ts
          JOIN transactions t ON t.id = ts.transaction_id
          WHERE t.bank_account_id = CAST(:accountId AS uuid)
            AND ts.category_id IN (SELECT id FROM envelope_cat_tree)
            AND ts.amount < 0
            AND t.transaction_date >= CAST(:from AS date)
            AND t.transaction_date < CAST(:to AS date)
          GROUP BY date_trunc('month', t.transaction_date)
      )
      SELECT m.month_start,
             COALESCE(d.consumed, 0) + COALESCE(s.consumed, 0) AS consumed
      FROM months m
      LEFT JOIN monthly_direct d ON d.month_start = m.month_start
      LEFT JOIN monthly_splits s ON s.month_start = m.month_start
      ORDER BY m.month_start
      """, nativeQuery = true)
  List<Object[]> findMonthlyConsumptionRange(
      @Param("envelopeId") UUID envelopeId,
      @Param("accountId") UUID accountId,
      @Param("from") LocalDate from,
      @Param("to") LocalDate to);

  /** Returns true when at least one EnvelopeAllocation exists for this envelope. Used to decide
   * hard-delete vs soft-delete (D-18). */
  @Query("""
      SELECT COUNT(ea) > 0 FROM EnvelopeAllocation ea
      WHERE ea.envelope.id = :envelopeId
      """)
  boolean hasAnyAllocation(@Param("envelopeId") UUID envelopeId);
}
```

Notes:
- Use `DISTINCT` because the `JOIN AccountAccess` could otherwise duplicate envelopes if a user has multiple access entries (defensive).
- Native SQL CTE uses `CAST(:envelopeId AS uuid)` per Pitfall 2 / TransactionRepository convention.
- `BigDecimal` return type for the SUM avoids precision loss; the service will wrap into `Money`.
- The 12-month query uses `generate_series` with `CAST(:to AS date) - INTERVAL '1 day'` so the end-exclusive `to` bound stays consistent (passing `:from = 2026-04-01`, `:to = 2027-04-01` yields exactly 12 buckets starting at 2026-04-01).
- `hasAnyAllocation` will be used by Plan 04 service to choose between hard delete and soft delete on DELETE.
- **NOT EXISTS dedup:** present in BOTH `sumConsumedForMonth` and `monthly_direct` of `findMonthlyConsumptionRange`. Without this, a transaction that has BOTH a non-null `category_id` AND child rows in `transaction_splits` would be counted twice (once via the transactions branch, once via the splits branch).
  </action>
  <verify>
    <automated>cd /home/negus/dev/prosperity && ./mvnw -pl backend test -Dtest=ProsperityApplicationTest -q 2>&1 | tail -20</automated>
  </verify>
  <acceptance_criteria>
    - `grep -c "findByAccountAccessibleToUser" backend/src/main/java/com/prosperity/envelope/EnvelopeRepository.java` returns 1
    - `grep -c "findAllAccessibleToUser" backend/src/main/java/com/prosperity/envelope/EnvelopeRepository.java` returns at least 2 (regular + IncludingArchived)
    - `grep -c "existsCategoryLinkOnAccount" backend/src/main/java/com/prosperity/envelope/EnvelopeRepository.java` returns 1
    - `grep -c "sumConsumedForMonth" backend/src/main/java/com/prosperity/envelope/EnvelopeRepository.java` returns 1
    - `grep -c "findMonthlyConsumptionRange" backend/src/main/java/com/prosperity/envelope/EnvelopeRepository.java` returns 1
    - `grep -c "hasAnyAllocation" backend/src/main/java/com/prosperity/envelope/EnvelopeRepository.java` returns 1
    - `grep -c "WITH RECURSIVE envelope_cat_tree" backend/src/main/java/com/prosperity/envelope/EnvelopeRepository.java` returns 2 (consumed + history)
    - `grep -c "CAST(:envelopeId AS uuid)" backend/src/main/java/com/prosperity/envelope/EnvelopeRepository.java` returns at least 2
    - `grep -c "JOIN AccountAccess aa ON aa.bankAccount = ba" backend/src/main/java/com/prosperity/envelope/EnvelopeRepository.java` returns at least 3 (one per accessible-to-user query)
    - `grep -c "NOT EXISTS" backend/src/main/java/com/prosperity/envelope/EnvelopeRepository.java` returns at least 2 (sumConsumedForMonth + monthly_direct in findMonthlyConsumptionRange)
    - `grep -c "FROM transaction_splits ts2" backend/src/main/java/com/prosperity/envelope/EnvelopeRepository.java` returns at least 2 (the dedup subquery in both native queries)
    - `./mvnw -pl backend test -Dtest=ProsperityApplicationTest -q` exits 0 (Spring Data JPA parses all JPQL queries at startup, native SQL is parsed lazily but the file must compile)
  </acceptance_criteria>
  <done>EnvelopeRepository declares all 7 query methods with NOT EXISTS dedup on the transactions branch; JPQL queries validate at Spring Data startup (named-query validation), file compiles cleanly.</done>
</task>

<task type="auto" tdd="false">
  <name>Task 4: Enrich EnvelopeAllocationRepository (month lookup + month range)</name>
  <files>backend/src/main/java/com/prosperity/envelope/EnvelopeAllocationRepository.java</files>
  <read_first>
    - backend/src/main/java/com/prosperity/envelope/EnvelopeAllocationRepository.java (current empty state)
    - backend/src/main/java/com/prosperity/envelope/EnvelopeAllocation.java (confirm field name: monthValue is the LocalDate, NOT month — the JPQL must use `monthValue`)
  </read_first>
  <action>
Replace the contents of `backend/src/main/java/com/prosperity/envelope/EnvelopeAllocationRepository.java` with the following complete file:

```java
package com.prosperity.envelope;

import java.time.LocalDate;
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

/** Spring Data JPA repository for EnvelopeAllocation entities (monthly budget overrides). */
public interface EnvelopeAllocationRepository extends JpaRepository<EnvelopeAllocation, UUID> {

  /**
   * Returns the override for a given envelope on a given month-start (LocalDate of day 1). Empty
   * when no override exists — service falls back to envelope.budget (D-08).
   */
  @Query("""
      SELECT ea FROM EnvelopeAllocation ea
      WHERE ea.envelope.id = :envelopeId
      AND ea.monthValue = :monthStart
      """)
  Optional<EnvelopeAllocation> findByEnvelopeIdAndMonthValue(
      @Param("envelopeId") UUID envelopeId, @Param("monthStart") LocalDate monthStart);

  /**
   * Returns all overrides for a given envelope inside a half-open month range [from, to) ordered
   * by month ascending. Used by the Envelope Details page to overlay budget per month for the
   * 12-month history.
   */
  @Query("""
      SELECT ea FROM EnvelopeAllocation ea
      WHERE ea.envelope.id = :envelopeId
      AND ea.monthValue >= :from
      AND ea.monthValue < :to
      ORDER BY ea.monthValue ASC
      """)
  List<EnvelopeAllocation> findByEnvelopeIdAndMonthRange(
      @Param("envelopeId") UUID envelopeId,
      @Param("from") LocalDate from,
      @Param("to") LocalDate to);

  /** Returns ALL overrides for an envelope (used by the override sub-dialog list). */
  List<EnvelopeAllocation> findByEnvelopeIdOrderByMonthValueAsc(UUID envelopeId);
}
```

Notes:
- The entity field is `monthValue` (LocalDate), NOT `month`. This matches the existing `EnvelopeAllocation.java` field declaration `@Column(name = "month") private LocalDate monthValue`. JPQL must reference the Java field name.
- UNIQUE(envelope_id, month) DB constraint already exists (V006). Spring Data will surface a `DataIntegrityViolationException` on duplicate inserts — Plan 05 controller will translate to 409.
  </action>
  <verify>
    <automated>cd /home/negus/dev/prosperity && ./mvnw -pl backend test -Dtest=ProsperityApplicationTest -q 2>&1 | tail -20</automated>
  </verify>
  <acceptance_criteria>
    - `grep -c "findByEnvelopeIdAndMonthValue" backend/src/main/java/com/prosperity/envelope/EnvelopeAllocationRepository.java` returns 1
    - `grep -c "findByEnvelopeIdAndMonthRange" backend/src/main/java/com/prosperity/envelope/EnvelopeAllocationRepository.java` returns 1
    - `grep -c "findByEnvelopeIdOrderByMonthValueAsc" backend/src/main/java/com/prosperity/envelope/EnvelopeAllocationRepository.java` returns 1
    - `grep -c "ea.monthValue" backend/src/main/java/com/prosperity/envelope/EnvelopeAllocationRepository.java` returns at least 3
    - `./mvnw -pl backend test -Dtest=ProsperityApplicationTest -q` exits 0 (named JPQL queries validated)
  </acceptance_criteria>
  <done>EnvelopeAllocationRepository declares the three query methods using monthValue field; Spring Data JPA validates JPQL at startup; ProsperityApplicationTest passes.</done>
</task>

</tasks>

<verification>
- Flyway log on Testcontainers PostgreSQL shows V014 + V015 applied successfully.
- `./mvnw -pl backend compile` exits 0 with the new entity field and repository methods.
- `./mvnw -pl backend test -Dtest=ProsperityApplicationTest` exits 0 (boot test triggers JPQL validation + Flyway migration on real PostgreSQL via Testcontainers).
- `./mvnw -pl backend test -Dtest=EnvelopeTest` still exits 0 (existing entity tests are not broken by added fields).
</verification>

<success_criteria>
- envelope_categories table exists with composite PK and ON DELETE CASCADE on envelope_id, ON DELETE RESTRICT on category_id.
- envelopes table has archived BOOLEAN NOT NULL DEFAULT FALSE.
- Envelope entity exposes Set<Category> categories via @ManyToMany and an archived flag with getter/setter, while preserving all prior fields and helper methods.
- EnvelopeRepository can list envelopes filtered by user access and archived state, enforces D-01 with existsCategoryLinkOnAccount, computes consumed via recursive CTE on transactions + transaction_splits with NOT EXISTS dedup on the transactions branch, and returns 12 monthly buckets in one query.
- EnvelopeAllocationRepository can lookup an override by month start, list overrides over a range, and list all overrides ordered by month.
- All boot tests pass on PostgreSQL via Testcontainers.
</success_criteria>

<output>
After completion, create `.planning/phases/06-envelope-budgets/06-01-data-layer-SUMMARY.md`.
</output>
