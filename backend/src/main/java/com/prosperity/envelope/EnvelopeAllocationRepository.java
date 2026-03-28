package com.prosperity.envelope;

import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;

/** Spring Data JPA repository for EnvelopeAllocation entities. */
public interface EnvelopeAllocationRepository extends JpaRepository<EnvelopeAllocation, UUID> {}
