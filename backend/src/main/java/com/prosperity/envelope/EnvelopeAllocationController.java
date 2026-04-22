package com.prosperity.envelope;

import com.prosperity.account.AccountAccessDeniedException;
import com.prosperity.account.AccountNotFoundException;
import jakarta.validation.Valid;
import java.security.Principal;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

/**
 * REST controller for envelope monthly allocation overrides. Endpoints:
 *
 * <ul>
 *   <li>{@code /api/envelopes/{id}/allocations} — list + create (envelope-scoped)
 *   <li>{@code /api/envelopes/allocations/{allocationId}} — update + delete (allocation-scoped)
 * </ul>
 */
@RestController
@RequestMapping("/api")
public class EnvelopeAllocationController {

  private final EnvelopeAllocationService allocationService;

  public EnvelopeAllocationController(EnvelopeAllocationService allocationService) {
    this.allocationService = allocationService;
  }

  @PostMapping("/envelopes/{id}/allocations")
  public ResponseEntity<EnvelopeAllocationResponse> createAllocation(
      @PathVariable("id") UUID envelopeId,
      @Valid @RequestBody EnvelopeAllocationRequest request,
      Principal principal) {
    EnvelopeAllocationResponse response =
        allocationService.createAllocation(envelopeId, request, principal.getName());
    return ResponseEntity.status(HttpStatus.CREATED).body(response);
  }

  @GetMapping("/envelopes/{id}/allocations")
  public List<EnvelopeAllocationResponse> listAllocations(
      @PathVariable("id") UUID envelopeId, Principal principal) {
    return allocationService.listAllocations(envelopeId, principal.getName());
  }

  @PutMapping("/envelopes/allocations/{allocationId}")
  public EnvelopeAllocationResponse updateAllocation(
      @PathVariable UUID allocationId,
      @Valid @RequestBody EnvelopeAllocationRequest request,
      Principal principal) {
    return allocationService.updateAllocation(allocationId, request, principal.getName());
  }

  @DeleteMapping("/envelopes/allocations/{allocationId}")
  @ResponseStatus(HttpStatus.NO_CONTENT)
  public void deleteAllocation(@PathVariable UUID allocationId, Principal principal) {
    allocationService.deleteAllocation(allocationId, principal.getName());
  }

  // ------------- Exception handlers -------------

  @ExceptionHandler(EnvelopeNotFoundException.class)
  @ResponseStatus(HttpStatus.NOT_FOUND)
  Map<String, String> handleEnvelopeNotFound(EnvelopeNotFoundException e) {
    return Map.of("error", e.getMessage());
  }

  @ExceptionHandler(EnvelopeAllocationNotFoundException.class)
  @ResponseStatus(HttpStatus.NOT_FOUND)
  Map<String, String> handleAllocationNotFound(EnvelopeAllocationNotFoundException e) {
    return Map.of("error", e.getMessage());
  }

  @ExceptionHandler(AccountNotFoundException.class)
  @ResponseStatus(HttpStatus.NOT_FOUND)
  Map<String, String> handleAccountNotFound(AccountNotFoundException e) {
    return Map.of("error", e.getMessage());
  }

  @ExceptionHandler(AccountAccessDeniedException.class)
  @ResponseStatus(HttpStatus.FORBIDDEN)
  Map<String, String> handleAccessDenied(AccountAccessDeniedException e) {
    return Map.of("error", e.getMessage());
  }

  /** Translates UNIQUE(envelope_id, month) violations into 409 Conflict. */
  @ExceptionHandler(DataIntegrityViolationException.class)
  @ResponseStatus(HttpStatus.CONFLICT)
  Map<String, String> handleDuplicate(DataIntegrityViolationException e) {
    return Map.of(
        "error", "Une personnalisation existe deja pour ce mois sur cette enveloppe");
  }
}
