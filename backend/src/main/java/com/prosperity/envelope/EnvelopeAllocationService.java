package com.prosperity.envelope;

import com.prosperity.account.AccessLevel;
import com.prosperity.account.AccountAccessDeniedException;
import com.prosperity.account.AccountNotFoundException;
import com.prosperity.account.AccountRepository;
import com.prosperity.auth.User;
import com.prosperity.auth.UserNotFoundException;
import com.prosperity.auth.UserRepository;
import com.prosperity.shared.Money;
import java.util.Arrays;
import java.util.List;
import java.util.UUID;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * Service for managing monthly budget overrides on envelopes (D-08, D-10).
 *
 * <p>Access checks inherit from the envelope's parent account via the same 403-vs-404 pattern used
 * in {@link EnvelopeService} (existsById check before access check). Duplicate (envelope, month)
 * violations are NOT caught here — they bubble up as {@link
 * org.springframework.dao.DataIntegrityViolationException} so that the controller's
 * {@code @ExceptionHandler} translates them to HTTP 409 Conflict.
 */
@Service
public class EnvelopeAllocationService {

  private final EnvelopeAllocationRepository allocationRepository;
  private final EnvelopeRepository envelopeRepository;
  private final AccountRepository accountRepository;
  private final UserRepository userRepository;

  public EnvelopeAllocationService(
      EnvelopeAllocationRepository allocationRepository,
      EnvelopeRepository envelopeRepository,
      AccountRepository accountRepository,
      UserRepository userRepository) {
    this.allocationRepository = allocationRepository;
    this.envelopeRepository = envelopeRepository;
    this.accountRepository = accountRepository;
    this.userRepository = userRepository;
  }

  /**
   * Creates a monthly override on an envelope. Throws {@link
   * org.springframework.dao.DataIntegrityViolationException} on duplicate (envelope, month) — the
   * controller maps that exception to 409 Conflict.
   *
   * @throws EnvelopeNotFoundException if the envelope does not exist (404)
   * @throws AccountAccessDeniedException if the user has no WRITE access on the envelope's account
   */
  @Transactional
  public EnvelopeAllocationResponse createAllocation(
      UUID envelopeId, EnvelopeAllocationRequest request, String userEmail) {
    User user = resolveUser(userEmail);
    Envelope envelope = requireEnvelopeAccess(envelopeId, user.getId(), AccessLevel.WRITE);

    EnvelopeAllocation allocation =
        new EnvelopeAllocation(envelope, request.month(), new Money(request.allocatedAmount()));
    allocationRepository.save(allocation);
    return toResponse(allocation);
  }

  /**
   * Lists all monthly overrides for an envelope, ordered by month ascending.
   *
   * @throws EnvelopeNotFoundException if the envelope does not exist (404)
   * @throws AccountAccessDeniedException if the user has no READ access on the envelope's account
   */
  @Transactional(readOnly = true)
  public List<EnvelopeAllocationResponse> listAllocations(UUID envelopeId, String userEmail) {
    User user = resolveUser(userEmail);
    requireEnvelopeAccess(envelopeId, user.getId(), AccessLevel.READ);
    return allocationRepository.findByEnvelopeIdOrderByMonthValueAsc(envelopeId).stream()
        .map(this::toResponse)
        .toList();
  }

  /**
   * Replaces the allocatedAmount of an existing allocation. Month is immutable — to change month
   * the caller must delete and re-create.
   *
   * @throws EnvelopeAllocationNotFoundException if the allocation does not exist (404)
   * @throws AccountAccessDeniedException if the user has no WRITE access on the envelope's account
   */
  @Transactional
  public EnvelopeAllocationResponse updateAllocation(
      UUID allocationId, EnvelopeAllocationRequest request, String userEmail) {
    User user = resolveUser(userEmail);
    EnvelopeAllocation allocation =
        allocationRepository
            .findById(allocationId)
            .orElseThrow(
                () ->
                    new EnvelopeAllocationNotFoundException(
                        "Allocation not found: " + allocationId));
    requireEnvelopeAccess(allocation.getEnvelope().getId(), user.getId(), AccessLevel.WRITE);
    allocation.setAllocatedAmount(new Money(request.allocatedAmount()));
    return toResponse(allocation);
  }

  /**
   * Deletes an allocation.
   *
   * @throws EnvelopeAllocationNotFoundException if the allocation does not exist (404)
   * @throws AccountAccessDeniedException if the user has no WRITE access on the envelope's account
   */
  @Transactional
  public void deleteAllocation(UUID allocationId, String userEmail) {
    User user = resolveUser(userEmail);
    EnvelopeAllocation allocation =
        allocationRepository
            .findById(allocationId)
            .orElseThrow(
                () ->
                    new EnvelopeAllocationNotFoundException(
                        "Allocation not found: " + allocationId));
    requireEnvelopeAccess(allocation.getEnvelope().getId(), user.getId(), AccessLevel.WRITE);
    allocationRepository.delete(allocation);
  }

  // ---------------------------------------------------------------------------
  // Private helpers (duplicated from EnvelopeService — duplication beats premature
  // abstraction; extract only if a third service needs the same logic).
  // ---------------------------------------------------------------------------

  private Envelope requireEnvelopeAccess(UUID envelopeId, UUID userId, AccessLevel required) {
    if (!envelopeRepository.existsById(envelopeId)) {
      throw new EnvelopeNotFoundException("Envelope not found: " + envelopeId);
    }
    Envelope envelope =
        envelopeRepository
            .findById(envelopeId)
            .orElseThrow(() -> new EnvelopeNotFoundException("Envelope not found: " + envelopeId));
    UUID accountId = envelope.getBankAccount().getId();
    if (!accountRepository.existsById(accountId)) {
      throw new AccountNotFoundException("Account not found: " + accountId);
    }
    List<AccessLevel> levels =
        Arrays.stream(AccessLevel.values()).filter(l -> l.isAtLeast(required)).toList();
    if (!accountRepository.hasAccess(accountId, userId, levels)) {
      throw new AccountAccessDeniedException("Access denied to account: " + accountId);
    }
    return envelope;
  }

  private User resolveUser(String userEmail) {
    return userRepository
        .findByEmail(userEmail)
        .orElseThrow(() -> new UserNotFoundException("User not found: " + userEmail));
  }

  private EnvelopeAllocationResponse toResponse(EnvelopeAllocation allocation) {
    return new EnvelopeAllocationResponse(
        allocation.getId(),
        allocation.getEnvelope().getId(),
        allocation.getMonth(),
        allocation.getAllocatedAmount().amount(),
        allocation.getCreatedAt());
  }
}
