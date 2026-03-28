package com.prosperity.envelope;

import com.prosperity.shared.Money;
import com.prosperity.shared.MoneyConverter;
import jakarta.persistence.Column;
import jakarta.persistence.Convert;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.Table;
import java.time.Instant;
import java.time.YearMonth;
import java.util.UUID;

/** JPA entity representing a monthly budget allocation for an envelope. */
@Entity
@Table(name = "envelope_allocations")
public class EnvelopeAllocation {

  @Id
  @GeneratedValue(strategy = GenerationType.UUID)
  private UUID id;

  @ManyToOne(optional = false)
  @JoinColumn(name = "envelope_id", nullable = false)
  private Envelope envelope;

  @Column(name = "month", nullable = false, length = 7)
  private String monthValue;

  @Convert(converter = MoneyConverter.class)
  @Column(name = "allocated_amount_cents")
  private Money allocatedAmount;

  @Column(name = "created_at", nullable = false, columnDefinition = "TIMESTAMPTZ")
  private Instant createdAt;

  protected EnvelopeAllocation() {}

  public EnvelopeAllocation(Envelope envelope, YearMonth month, Money allocatedAmount) {
    this.envelope = envelope;
    this.monthValue = month.toString();
    this.allocatedAmount = allocatedAmount;
    this.createdAt = Instant.now();
  }

  public UUID getId() {
    return id;
  }

  public void setId(UUID id) {
    this.id = id;
  }

  public Envelope getEnvelope() {
    return envelope;
  }

  public void setEnvelope(Envelope envelope) {
    this.envelope = envelope;
  }

  public YearMonth getMonth() {
    return YearMonth.parse(monthValue);
  }

  public void setMonth(YearMonth month) {
    this.monthValue = month.toString();
  }

  public Money getAllocatedAmount() {
    return allocatedAmount;
  }

  public void setAllocatedAmount(Money allocatedAmount) {
    this.allocatedAmount = allocatedAmount;
  }

  public Instant getCreatedAt() {
    return createdAt;
  }

  public void setCreatedAt(Instant createdAt) {
    this.createdAt = createdAt;
  }
}
