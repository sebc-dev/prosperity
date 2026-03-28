package com.prosperity.envelope;

import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;

/** Spring Data JPA repository for Envelope entities. */
public interface EnvelopeRepository extends JpaRepository<Envelope, UUID> {}
