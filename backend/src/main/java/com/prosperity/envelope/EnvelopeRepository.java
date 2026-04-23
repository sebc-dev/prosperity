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
   * Returns non-archived envelopes for a single account, accessible to the user. Used by GET
   * /api/accounts/{accountId}/envelopes.
   */
  @Query(
      """
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

  /**
   * Returns all non-archived envelopes accessible to the user across every account they have access
   * to. Used by GET /api/envelopes (no accountId filter).
   */
  @Query(
      """
      SELECT e FROM Envelope e
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
  @Query(
      """
      SELECT e FROM Envelope e
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
  @Query(
      """
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
   * any transaction that has at least one row in transaction_splits — those are aggregated via the
   * splits branch only. Phase 5 D-06 says split parents have {@code category_id = NULL} so they
   * wouldn't match the IN clause anyway, but the NOT EXISTS guard makes the dedup independent of
   * that convention (defensive against future import code that leaves both populated).
   *
   * <p>Convention: consumed is returned as a NON-NEGATIVE BigDecimal (we negate the negative
   * amounts). A refund (positive amount) in a tracked category REDUCES consumed because we treat
   * positive amounts symmetrically via -t.amount when t.amount &gt; 0 in the negation step. To keep
   * semantics simple, this query SUMS only negative amounts and negates them — refunds are
   * documented as out of v1 scope (Open Question 1 in RESEARCH.md, planner default = filter
   * spending only).
   */
  @Query(
      value =
          """
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
      """,
      nativeQuery = true)
  BigDecimal sumConsumedForMonth(
      @Param("envelopeId") UUID envelopeId,
      @Param("accountId") UUID accountId,
      @Param("monthStart") LocalDate monthStart,
      @Param("nextMonthStart") LocalDate nextMonthStart);

  /**
   * Returns 12 month-buckets of consumption between [from, to). Each row: [month_start (date),
   * consumed (numeric)]. Months without transactions in linked categories return consumed = 0 (LEFT
   * JOIN preserves the bucket from generate_series). Used for the Envelope Details page 12-month
   * history table (ENVL-06). Same NOT EXISTS dedup as sumConsumedForMonth (split parents counted
   * only via the splits branch).
   */
  @Query(
      value =
          """
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
      """,
      nativeQuery = true)
  List<Object[]> findMonthlyConsumptionRange(
      @Param("envelopeId") UUID envelopeId,
      @Param("accountId") UUID accountId,
      @Param("from") LocalDate from,
      @Param("to") LocalDate to);

  /**
   * Returns true when at least one EnvelopeAllocation exists for this envelope. Used to decide
   * hard-delete vs soft-delete (D-18).
   */
  @Query(
      """
      SELECT COUNT(ea) > 0 FROM EnvelopeAllocation ea
      WHERE ea.envelope.id = :envelopeId
      """)
  boolean hasAnyAllocation(@Param("envelopeId") UUID envelopeId);
}
