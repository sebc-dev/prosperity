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
  @Query(
      """
      SELECT ea FROM EnvelopeAllocation ea
      WHERE ea.envelope.id = :envelopeId
      AND ea.monthValue = :monthStart
      """)
  Optional<EnvelopeAllocation> findByEnvelopeIdAndMonthValue(
      @Param("envelopeId") UUID envelopeId, @Param("monthStart") LocalDate monthStart);

  /**
   * Returns all overrides for a given envelope inside a half-open month range [from, to) ordered by
   * month ascending. Used by the Envelope Details page to overlay budget per month for the 12-month
   * history.
   */
  @Query(
      """
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
