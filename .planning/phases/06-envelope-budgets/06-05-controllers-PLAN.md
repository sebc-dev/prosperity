---
phase: 06-envelope-budgets
plan: 05
type: execute
wave: 2
depends_on:
  - 06-01-data-layer-PLAN.md
  - 06-02-dtos-and-exceptions-PLAN.md
  - 06-04-service-layer-PLAN.md
files_modified:
  - backend/src/main/java/com/prosperity/envelope/EnvelopeController.java
  - backend/src/main/java/com/prosperity/envelope/EnvelopeAllocationController.java
autonomous: true
requirements:
  - ENVL-01
  - ENVL-02
  - ENVL-06
  - ENVL-07
must_haves:
  truths:
    - "POST /api/accounts/{accountId}/envelopes creates an envelope on the account; returns 201 with EnvelopeResponse"
    - "GET /api/accounts/{accountId}/envelopes lists envelopes accessible to current user on this account; supports ?includeArchived=true"
    - "GET /api/envelopes lists envelopes accessible to current user across all their accounts; supports ?includeArchived=true and ?accountId=<uuid>"
    - "GET /api/envelopes/{id} returns the EnvelopeResponse with current-month consumed/available/ratio/status"
    - "PUT /api/envelopes/{id} partial-PATCH semantics, returns 200 with updated EnvelopeResponse"
    - "DELETE /api/envelopes/{id} returns 204; soft-delete vs hard-delete is invisible to the API caller"
    - "GET /api/envelopes/{id}/history?month=YYYY-MM returns the 12-month history ending at the given month (defaults to current month)"
    - "POST /api/envelopes/{id}/allocations creates a monthly override; returns 201; duplicate (envelope,month) returns 409"
    - "GET /api/envelopes/{id}/allocations lists overrides ordered by month asc"
    - "PUT /api/envelopes/allocations/{allocationId} replaces allocatedAmount; returns 200"
    - "DELETE /api/envelopes/allocations/{allocationId} returns 204"
    - "Exception handlers translate EnvelopeNotFoundException -> 404, AccountAccessDeniedException -> 403, DuplicateEnvelopeCategoryException -> 409, DataIntegrityViolationException on allocations -> 409, AccountNotFoundException -> 404, CategoryNotFoundException -> 404, EnvelopeAllocationNotFoundException -> 404"
  artifacts:
    - path: "backend/src/main/java/com/prosperity/envelope/EnvelopeController.java"
      provides: "REST endpoints for envelope CRUD + history"
      contains: "EnvelopeController"
    - path: "backend/src/main/java/com/prosperity/envelope/EnvelopeAllocationController.java"
      provides: "REST endpoints for monthly override CRUD"
      contains: "EnvelopeAllocationController"
  key_links:
    - from: "EnvelopeController endpoints"
      to: "EnvelopeService methods"
      via: "constructor injection"
      pattern: "envelopeService\\.(createEnvelope|listEnvelopesForAccount|listAllEnvelopes|getEnvelope|updateEnvelope|deleteEnvelope|getEnvelopeHistory)"
    - from: "Exception handlers"
      to: "HTTP status codes"
      via: "@ResponseStatus(HttpStatus.X) on @ExceptionHandler"
      pattern: "@ExceptionHandler"
---

<objective>
Wire the EnvelopeService and EnvelopeAllocationService to REST. Two controllers: one for envelopes, one for allocations. Each is thin — delegates to the service, maps exceptions to HTTP statuses via `@ExceptionHandler`. Pattern lifted verbatim from Phase 5 TransactionController.

Purpose: Plan 04 services are now reachable from the frontend. Closes ENVL-01, ENVL-02, ENVL-06, ENVL-07 on the API surface.

Output: 2 controller classes, fully implemented with exception handlers.
</objective>

<execution_context>
@/home/negus/dev/prosperity/.claude/get-shit-done/workflows/execute-plan.md
@/home/negus/dev/prosperity/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT.md
@.planning/ROADMAP.md
@.planning/phases/06-envelope-budgets/06-CONTEXT.md
@.planning/phases/06-envelope-budgets/06-RESEARCH.md
@.planning/phases/06-envelope-budgets/06-04-service-layer-PLAN.md

@backend/src/main/java/com/prosperity/transaction/TransactionController.java
@backend/src/main/java/com/prosperity/account/AccountController.java
@backend/src/main/java/com/prosperity/envelope/EnvelopeService.java
@backend/src/main/java/com/prosperity/envelope/EnvelopeAllocationService.java
@backend/src/main/java/com/prosperity/envelope/EnvelopeNotFoundException.java
@backend/src/main/java/com/prosperity/envelope/EnvelopeAllocationNotFoundException.java
@backend/src/main/java/com/prosperity/envelope/DuplicateEnvelopeCategoryException.java

<interfaces>
EnvelopeService public methods (Plan 04):
- createEnvelope(UUID accountId, CreateEnvelopeRequest, String userEmail) -> EnvelopeResponse
- listEnvelopesForAccount(UUID accountId, boolean includeArchived, String userEmail) -> List<EnvelopeResponse>
- listAllEnvelopes(boolean includeArchived, String userEmail) -> List<EnvelopeResponse>
- getEnvelope(UUID envelopeId, String userEmail) -> EnvelopeResponse
- updateEnvelope(UUID envelopeId, UpdateEnvelopeRequest, String userEmail) -> EnvelopeResponse
- deleteEnvelope(UUID envelopeId, String userEmail) -> void
- getEnvelopeHistory(UUID envelopeId, YearMonth monthInclusive, String userEmail) -> List<EnvelopeHistoryEntry>

EnvelopeAllocationService public methods:
- createAllocation(UUID envelopeId, EnvelopeAllocationRequest, String userEmail) -> EnvelopeAllocationResponse
- listAllocations(UUID envelopeId, String userEmail) -> List<EnvelopeAllocationResponse>
- updateAllocation(UUID allocationId, EnvelopeAllocationRequest, String userEmail) -> EnvelopeAllocationResponse
- deleteAllocation(UUID allocationId, String userEmail) -> void

TransactionController exception handler pattern:
```java
@ExceptionHandler(AccountAccessDeniedException.class)
@ResponseStatus(HttpStatus.FORBIDDEN)
Map<String, String> handleAccessDenied(AccountAccessDeniedException e) {
  return Map.of("error", e.getMessage());
}
```
</interfaces>
</context>

<tasks>

<task type="auto" tdd="false">
  <name>Task 1: EnvelopeController (CRUD + history) with exception handlers</name>
  <files>backend/src/main/java/com/prosperity/envelope/EnvelopeController.java</files>
  <read_first>
    - backend/src/main/java/com/prosperity/transaction/TransactionController.java (canonical structure: dual base path /api, @ExceptionHandler block at bottom, Principal for userEmail)
    - backend/src/main/java/com/prosperity/account/AccountController.java (alternate canonical structure for cross-checking)
    - backend/src/main/java/com/prosperity/envelope/EnvelopeService.java (Plan 04 — exact method signatures to call)
    - backend/src/main/java/com/prosperity/envelope/EnvelopeNotFoundException.java
    - backend/src/main/java/com/prosperity/envelope/DuplicateEnvelopeCategoryException.java
  </read_first>
  <action>
Create `backend/src/main/java/com/prosperity/envelope/EnvelopeController.java` with these endpoints and handlers exactly:

```java
package com.prosperity.envelope;

import com.prosperity.account.AccountAccessDeniedException;
import com.prosperity.account.AccountNotFoundException;
import com.prosperity.category.CategoryNotFoundException;
import jakarta.validation.Valid;
import java.security.Principal;
import java.time.YearMonth;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.springframework.format.annotation.DateTimeFormat;
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
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

/**
 * REST controller for envelope endpoints. Endpoints span:
 *
 * <ul>
 *   <li>{@code /api/accounts/{accountId}/envelopes} — list + create scoped to an account
 *   <li>{@code /api/envelopes} — list across all accounts the user has access to
 *   <li>{@code /api/envelopes/{id}} — get/update/delete + history
 * </ul>
 *
 * <p>403 vs 404 follows Phase 3/5 convention: existsById(account) -> 404 if missing, then 403 if
 * caller has no access.
 */
@RestController
@RequestMapping("/api")
public class EnvelopeController {

  private final EnvelopeService envelopeService;

  public EnvelopeController(EnvelopeService envelopeService) {
    this.envelopeService = envelopeService;
  }

  // ------------------ Account-scoped --------------------------------

  @PostMapping("/accounts/{accountId}/envelopes")
  public ResponseEntity<EnvelopeResponse> createEnvelope(
      @PathVariable UUID accountId,
      @Valid @RequestBody CreateEnvelopeRequest request,
      Principal principal) {
    EnvelopeResponse response =
        envelopeService.createEnvelope(accountId, request, principal.getName());
    return ResponseEntity.status(HttpStatus.CREATED).body(response);
  }

  @GetMapping("/accounts/{accountId}/envelopes")
  public List<EnvelopeResponse> listEnvelopesForAccount(
      @PathVariable UUID accountId,
      @RequestParam(name = "includeArchived", defaultValue = "false") boolean includeArchived,
      Principal principal) {
    return envelopeService.listEnvelopesForAccount(
        accountId, includeArchived, principal.getName());
  }

  // ------------------ Cross-account list ---------------------------

  @GetMapping("/envelopes")
  public List<EnvelopeResponse> listEnvelopes(
      @RequestParam(name = "accountId", required = false) UUID accountId,
      @RequestParam(name = "includeArchived", defaultValue = "false") boolean includeArchived,
      Principal principal) {
    if (accountId != null) {
      return envelopeService.listEnvelopesForAccount(
          accountId, includeArchived, principal.getName());
    }
    return envelopeService.listAllEnvelopes(includeArchived, principal.getName());
  }

  // ------------------ Envelope-scoped ------------------------------

  @GetMapping("/envelopes/{id}")
  public EnvelopeResponse getEnvelope(@PathVariable UUID id, Principal principal) {
    return envelopeService.getEnvelope(id, principal.getName());
  }

  @PutMapping("/envelopes/{id}")
  public EnvelopeResponse updateEnvelope(
      @PathVariable UUID id,
      @Valid @RequestBody UpdateEnvelopeRequest request,
      Principal principal) {
    return envelopeService.updateEnvelope(id, request, principal.getName());
  }

  @DeleteMapping("/envelopes/{id}")
  @ResponseStatus(HttpStatus.NO_CONTENT)
  public void deleteEnvelope(@PathVariable UUID id, Principal principal) {
    envelopeService.deleteEnvelope(id, principal.getName());
  }

  /**
   * Returns the 12-month consumption history ending at {@code month} (defaults to current month).
   * The {@code month} request param is parsed as {@code yyyy-MM} (ISO 8601 month).
   */
  @GetMapping("/envelopes/{id}/history")
  public List<EnvelopeHistoryEntry> getHistory(
      @PathVariable UUID id,
      @RequestParam(name = "month", required = false)
          @DateTimeFormat(pattern = "yyyy-MM")
          YearMonth month,
      Principal principal) {
    YearMonth target = month != null ? month : YearMonth.now();
    return envelopeService.getEnvelopeHistory(id, target, principal.getName());
  }

  // ------------------ Exception handlers ----------------------------

  @ExceptionHandler(EnvelopeNotFoundException.class)
  @ResponseStatus(HttpStatus.NOT_FOUND)
  Map<String, String> handleEnvelopeNotFound(EnvelopeNotFoundException e) {
    return Map.of("error", e.getMessage());
  }

  @ExceptionHandler(AccountNotFoundException.class)
  @ResponseStatus(HttpStatus.NOT_FOUND)
  Map<String, String> handleAccountNotFound(AccountNotFoundException e) {
    return Map.of("error", e.getMessage());
  }

  @ExceptionHandler(CategoryNotFoundException.class)
  @ResponseStatus(HttpStatus.NOT_FOUND)
  Map<String, String> handleCategoryNotFound(CategoryNotFoundException e) {
    return Map.of("error", e.getMessage());
  }

  @ExceptionHandler(AccountAccessDeniedException.class)
  @ResponseStatus(HttpStatus.FORBIDDEN)
  Map<String, String> handleAccessDenied(AccountAccessDeniedException e) {
    return Map.of("error", e.getMessage());
  }

  @ExceptionHandler(DuplicateEnvelopeCategoryException.class)
  @ResponseStatus(HttpStatus.CONFLICT)
  Map<String, String> handleDuplicateCategory(DuplicateEnvelopeCategoryException e) {
    return Map.of("error", e.getMessage());
  }
}
```

Notes:
- `@DateTimeFormat(pattern = "yyyy-MM")` enables Spring's automatic `YearMonth` binding from query params (Spring Boot 4 supports this out of the box).
- DELETE returns 204 (no body) per REST convention; service hides hard-vs-soft delete distinction.
- Exception handlers return `Map<String, String>` (matches existing TransactionController style).
  </action>
  <verify>
    <automated>cd /home/negus/dev/prosperity && ./mvnw -pl backend compile -q 2>&1 | tail -10</automated>
  </verify>
  <acceptance_criteria>
    - File `backend/src/main/java/com/prosperity/envelope/EnvelopeController.java` exists
    - `grep -c "@RestController" backend/src/main/java/com/prosperity/envelope/EnvelopeController.java` returns 1
    - `grep -c "@RequestMapping(\"/api\")" backend/src/main/java/com/prosperity/envelope/EnvelopeController.java` returns 1
    - `grep -c "@PostMapping(\"/accounts/{accountId}/envelopes\")" backend/src/main/java/com/prosperity/envelope/EnvelopeController.java` returns 1
    - `grep -c "@GetMapping(\"/accounts/{accountId}/envelopes\")" backend/src/main/java/com/prosperity/envelope/EnvelopeController.java` returns 1
    - `grep -c "@GetMapping(\"/envelopes\")" backend/src/main/java/com/prosperity/envelope/EnvelopeController.java` returns 1
    - `grep -c "@GetMapping(\"/envelopes/{id}\")" backend/src/main/java/com/prosperity/envelope/EnvelopeController.java` returns 1
    - `grep -c "@PutMapping(\"/envelopes/{id}\")" backend/src/main/java/com/prosperity/envelope/EnvelopeController.java` returns 1
    - `grep -c "@DeleteMapping(\"/envelopes/{id}\")" backend/src/main/java/com/prosperity/envelope/EnvelopeController.java` returns 1
    - `grep -c "@GetMapping(\"/envelopes/{id}/history\")" backend/src/main/java/com/prosperity/envelope/EnvelopeController.java` returns 1
    - `grep -c "HttpStatus.NO_CONTENT" backend/src/main/java/com/prosperity/envelope/EnvelopeController.java` returns 1
    - `grep -c "HttpStatus.CREATED" backend/src/main/java/com/prosperity/envelope/EnvelopeController.java` returns 1
    - `grep -c "@ExceptionHandler(EnvelopeNotFoundException.class)" backend/src/main/java/com/prosperity/envelope/EnvelopeController.java` returns 1
    - `grep -c "@ExceptionHandler(AccountAccessDeniedException.class)" backend/src/main/java/com/prosperity/envelope/EnvelopeController.java` returns 1
    - `grep -c "@ExceptionHandler(DuplicateEnvelopeCategoryException.class)" backend/src/main/java/com/prosperity/envelope/EnvelopeController.java` returns 1
    - `grep -c "HttpStatus.CONFLICT" backend/src/main/java/com/prosperity/envelope/EnvelopeController.java` returns 1
    - `grep -c "HttpStatus.FORBIDDEN" backend/src/main/java/com/prosperity/envelope/EnvelopeController.java` returns 1
    - `grep -c "HttpStatus.NOT_FOUND" backend/src/main/java/com/prosperity/envelope/EnvelopeController.java` returns 1
    - `grep -c "@DateTimeFormat(pattern = \"yyyy-MM\")" backend/src/main/java/com/prosperity/envelope/EnvelopeController.java` returns 1
    - `./mvnw -pl backend compile -q` exits 0
  </acceptance_criteria>
  <done>EnvelopeController exposes 8 routes, includes 5 exception handlers covering 404 / 403 / 409 mappings; DELETE returns 204; YearMonth query param parses yyyy-MM; file compiles.</done>
</task>

<task type="auto" tdd="false">
  <name>Task 2: EnvelopeAllocationController + DataIntegrityViolation -> 409 mapping</name>
  <files>backend/src/main/java/com/prosperity/envelope/EnvelopeAllocationController.java</files>
  <read_first>
    - backend/src/main/java/com/prosperity/transaction/TransactionController.java (exception handler block style)
    - backend/src/main/java/com/prosperity/envelope/EnvelopeAllocationService.java (Plan 04 — methods to call)
    - backend/src/main/java/com/prosperity/envelope/EnvelopeAllocationNotFoundException.java
  </read_first>
  <action>
Create `backend/src/main/java/com/prosperity/envelope/EnvelopeAllocationController.java`:

```java
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
```

Notes:
- `@ExceptionHandler(DataIntegrityViolationException.class)` is scoped to THIS controller only (not @ControllerAdvice) so it doesn't affect other controllers.
- Allocation routes deliberately separate from the EnvelopeController to keep file sizes review-friendly (atomic decoupling principle).
  </action>
  <verify>
    <automated>cd /home/negus/dev/prosperity && ./mvnw -pl backend test -Dtest=ProsperityApplicationTest -q 2>&1 | tail -20</automated>
  </verify>
  <acceptance_criteria>
    - File `backend/src/main/java/com/prosperity/envelope/EnvelopeAllocationController.java` exists
    - `grep -c "@RestController" backend/src/main/java/com/prosperity/envelope/EnvelopeAllocationController.java` returns 1
    - `grep -c "@PostMapping(\"/envelopes/{id}/allocations\")" backend/src/main/java/com/prosperity/envelope/EnvelopeAllocationController.java` returns 1
    - `grep -c "@GetMapping(\"/envelopes/{id}/allocations\")" backend/src/main/java/com/prosperity/envelope/EnvelopeAllocationController.java` returns 1
    - `grep -c "@PutMapping(\"/envelopes/allocations/{allocationId}\")" backend/src/main/java/com/prosperity/envelope/EnvelopeAllocationController.java` returns 1
    - `grep -c "@DeleteMapping(\"/envelopes/allocations/{allocationId}\")" backend/src/main/java/com/prosperity/envelope/EnvelopeAllocationController.java` returns 1
    - `grep -c "@ExceptionHandler(DataIntegrityViolationException.class)" backend/src/main/java/com/prosperity/envelope/EnvelopeAllocationController.java` returns 1
    - `grep -c "HttpStatus.CONFLICT" backend/src/main/java/com/prosperity/envelope/EnvelopeAllocationController.java` returns 1
    - `grep -c "HttpStatus.NO_CONTENT" backend/src/main/java/com/prosperity/envelope/EnvelopeAllocationController.java` returns 1
    - `grep -c "HttpStatus.CREATED" backend/src/main/java/com/prosperity/envelope/EnvelopeAllocationController.java` returns 1
    - `./mvnw -pl backend test -Dtest=ProsperityApplicationTest -q` exits 0 (Spring boot starts, both controllers register their routes, JPQL validates)
  </acceptance_criteria>
  <done>EnvelopeAllocationController exposes 4 routes, 5 exception handlers (including DataIntegrityViolation -> 409); ProsperityApplicationTest still passes (Spring boot starts cleanly with both controllers registered).</done>
</task>

</tasks>

<verification>
- `./mvnw -pl backend compile` exits 0.
- `./mvnw -pl backend test -Dtest=ProsperityApplicationTest` exits 0 (Spring boot starts with both controllers registered + Flyway applies V014/V015 + Spring Data validates JPQL queries).
- Manual smoke (Plan 06 will automate): a `mvn spring-boot:run` exposes /api/envelopes endpoints visible in Swagger UI / actuator mappings.
</verification>

<success_criteria>
- EnvelopeController + EnvelopeAllocationController exist with all routes and exception handlers above.
- DELETE returns 204; POST returns 201; GET/PUT return 200; conflict returns 409; access denied returns 403; not found returns 404.
- Spring boot starts cleanly with both controllers registered.
</success_criteria>

<output>
After completion, create `.planning/phases/06-envelope-budgets/06-05-controllers-SUMMARY.md`.
</output>
