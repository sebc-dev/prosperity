---
phase: 06-envelope-budgets
plan: 02
type: execute
wave: 1
depends_on: []
files_modified:
  - backend/src/main/java/com/prosperity/envelope/EnvelopeStatus.java
  - backend/src/main/java/com/prosperity/envelope/CreateEnvelopeRequest.java
  - backend/src/main/java/com/prosperity/envelope/UpdateEnvelopeRequest.java
  - backend/src/main/java/com/prosperity/envelope/EnvelopeAllocationRequest.java
  - backend/src/main/java/com/prosperity/envelope/EnvelopeResponse.java
  - backend/src/main/java/com/prosperity/envelope/EnvelopeAllocationResponse.java
  - backend/src/main/java/com/prosperity/envelope/EnvelopeHistoryEntry.java
  - backend/src/main/java/com/prosperity/envelope/EnvelopeNotFoundException.java
  - backend/src/main/java/com/prosperity/envelope/EnvelopeAllocationNotFoundException.java
  - backend/src/main/java/com/prosperity/envelope/DuplicateEnvelopeCategoryException.java
autonomous: true
requirements:
  - ENVL-01
  - ENVL-02
  - ENVL-05
  - ENVL-06
  - ENVL-07
must_haves:
  truths:
    - "EnvelopeStatus enum exists with values GREEN, YELLOW, RED"
    - "CreateEnvelopeRequest record has fields name, categoryIds (Set<UUID>), budget (BigDecimal), rolloverPolicy (RolloverPolicy) with bean validation"
    - "CreateEnvelopeRequest does NOT have a scope field (scope is derived server-side per D-07, Pitfall 4)"
    - "UpdateEnvelopeRequest is partial-PATCH (all-nullable fields) per Phase 3 D-08 convention"
    - "EnvelopeAllocationRequest has month (YearMonth) + allocatedAmount (BigDecimal) with @NotNull"
    - "EnvelopeResponse exposes id, bankAccountId, bankAccountName, name, scope, ownerId (nullable), categories (List<EnvelopeCategoryRef> with id+name), defaultBudget, effectiveBudget, consumed, available, ratio, status, rolloverPolicy, hasMonthlyOverride, archived, createdAt"
    - "EnvelopeHistoryEntry exposes month (YearMonth), effectiveBudget, consumed, available, ratio, status"
    - "EnvelopeNotFoundException, EnvelopeAllocationNotFoundException are RuntimeException subclasses (404 mapping)"
    - "DuplicateEnvelopeCategoryException is RuntimeException subclass for D-01 violations (409 mapping)"
  artifacts:
    - path: "backend/src/main/java/com/prosperity/envelope/EnvelopeStatus.java"
      provides: "Server-computed status enum (D-13 single source of truth)"
      contains: "enum EnvelopeStatus"
    - path: "backend/src/main/java/com/prosperity/envelope/EnvelopeResponse.java"
      provides: "Envelope read DTO with all UI-needed fields"
      contains: "EnvelopeStatus status"
    - path: "backend/src/main/java/com/prosperity/envelope/CreateEnvelopeRequest.java"
      provides: "Create payload (no scope field per Pitfall 4)"
      contains: "categoryIds"
    - path: "backend/src/main/java/com/prosperity/envelope/EnvelopeAllocationRequest.java"
      provides: "Monthly override payload"
      contains: "YearMonth month"
    - path: "backend/src/main/java/com/prosperity/envelope/DuplicateEnvelopeCategoryException.java"
      provides: "D-01 enforcement signal -> 409"
      contains: "extends RuntimeException"
  key_links:
    - from: "EnvelopeResponse"
      to: "EnvelopeStatus"
      via: "field of type EnvelopeStatus"
      pattern: "EnvelopeStatus status"
    - from: "EnvelopeHistoryEntry"
      to: "YearMonth"
      via: "month field"
      pattern: "YearMonth month"
---

<objective>
Define every DTO record, the EnvelopeStatus enum, and the three custom exceptions that the service (Plan 04) and controllers (Plan 05) need. Single concern: contracts.

Purpose: Lets the service implementation in Plan 04 work against final contracts (no rework when controllers come online in Plan 05). Runs in parallel with Plan 01 because no dependency between data layer changes and DTO declarations exists.

Output: 10 small Java files (records + enum + 3 exceptions). All compile cleanly.
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
@.planning/phases/06-envelope-budgets/06-UI-SPEC.md

@backend/src/main/java/com/prosperity/account/AccountResponse.java
@backend/src/main/java/com/prosperity/account/CreateAccountRequest.java
@backend/src/main/java/com/prosperity/account/UpdateAccountRequest.java
@backend/src/main/java/com/prosperity/transaction/TransactionResponse.java
@backend/src/main/java/com/prosperity/transaction/CreateTransactionRequest.java
@backend/src/main/java/com/prosperity/transaction/UpdateTransactionRequest.java
@backend/src/main/java/com/prosperity/account/AccountNotFoundException.java
@backend/src/main/java/com/prosperity/account/AccountAccessDeniedException.java
@backend/src/main/java/com/prosperity/category/DuplicateCategoryNameException.java

<revision_note>
**Iteration 1 revision:** D-13 ratio formula updated to use `effectiveBudget + carryOver` (the total allocatable amount) as denominator per BLOCKER 1, Option A. EnvelopeResponse Javadoc updated to reflect: ratio = consumed / (effectiveBudget + carryOver). Aligns with CONTEXT.md D-13 literal definition; the field semantics row 'available = effectiveBudget + carryOver - consumed' makes 'available' the signed remainder, while ratio uses the *allocatable* total (pre-consumption) so 0% means nothing spent and 100% means perfectly consumed.
</revision_note>

<interfaces>
RolloverPolicy enum (com.prosperity.shared.RolloverPolicy): RESET, CARRY_OVER
EnvelopeScope enum (com.prosperity.shared.EnvelopeScope): PERSONAL, SHARED
AccountType enum (com.prosperity.shared.AccountType): PERSONAL, SHARED

Phase 3 convention for partial-PATCH (UpdateAccountRequest): all fields nullable, service treats null as "no change".

Phase 3/5 exception pattern: simple `extends RuntimeException` with a single String message constructor; no error code field (controller's @ExceptionHandler maps to HttpStatus).
</interfaces>
</context>

<tasks>

<task type="auto" tdd="false">
  <name>Task 1: EnvelopeStatus enum + DTO records (Create/Update/Allocation requests, Envelope/Allocation/History responses)</name>
  <files>backend/src/main/java/com/prosperity/envelope/EnvelopeStatus.java, backend/src/main/java/com/prosperity/envelope/CreateEnvelopeRequest.java, backend/src/main/java/com/prosperity/envelope/UpdateEnvelopeRequest.java, backend/src/main/java/com/prosperity/envelope/EnvelopeAllocationRequest.java, backend/src/main/java/com/prosperity/envelope/EnvelopeResponse.java, backend/src/main/java/com/prosperity/envelope/EnvelopeAllocationResponse.java, backend/src/main/java/com/prosperity/envelope/EnvelopeHistoryEntry.java</files>
  <read_first>
    - backend/src/main/java/com/prosperity/transaction/CreateTransactionRequest.java (validation annotations style)
    - backend/src/main/java/com/prosperity/transaction/UpdateTransactionRequest.java (partial PATCH all-nullable convention)
    - backend/src/main/java/com/prosperity/account/AccountResponse.java (response record style + accessLevel field pattern)
    - backend/src/main/java/com/prosperity/transaction/TransactionResponse.java (record DTO with nested list pattern)
    - backend/src/main/java/com/prosperity/shared/RolloverPolicy.java (enum values)
    - backend/src/main/java/com/prosperity/shared/EnvelopeScope.java (enum values)
  </read_first>
  <action>
Create the following 7 files exactly as specified.

**File 1: `backend/src/main/java/com/prosperity/envelope/EnvelopeStatus.java`**

```java
package com.prosperity.envelope;

/**
 * Server-computed envelope status (D-13). Derived from the consumed/allocatable ratio. Frontend
 * maps 1:1 to a PrimeNG p-tag severity (GREEN -> success, YELLOW -> warn, RED -> danger).
 * Thresholds are owned by the service layer (single source of truth) — frontend NEVER recomputes
 * thresholds, it only translates the enum to a severity string.
 *
 * <p>Boundaries (ratio = consumed / (effectiveBudget + carryOver), per D-13):
 *
 * <ul>
 *   <li>{@link #GREEN}: ratio &lt; 0.80
 *   <li>{@link #YELLOW}: 0.80 &le; ratio &le; 1.00
 *   <li>{@link #RED}: ratio &gt; 1.00
 * </ul>
 */
public enum EnvelopeStatus {
  GREEN,
  YELLOW,
  RED
}
```

**File 2: `backend/src/main/java/com/prosperity/envelope/CreateEnvelopeRequest.java`**

```java
package com.prosperity.envelope;

import com.prosperity.shared.RolloverPolicy;
import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;
import java.math.BigDecimal;
import java.util.Set;
import java.util.UUID;

/**
 * Create-envelope request body. Note: NO {@code scope} field — scope is DERIVED server-side from
 * the target account's accountType (D-07, Pitfall 4). Account id is taken from the URL path.
 */
public record CreateEnvelopeRequest(
    @NotBlank @Size(max = 100) String name,
    @NotEmpty Set<@NotNull UUID> categoryIds,
    @NotNull @DecimalMin(value = "0.00", inclusive = true) BigDecimal budget,
    @NotNull RolloverPolicy rolloverPolicy) {}
```

**File 3: `backend/src/main/java/com/prosperity/envelope/UpdateEnvelopeRequest.java`**

```java
package com.prosperity.envelope;

import com.prosperity.shared.RolloverPolicy;
import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.Size;
import java.math.BigDecimal;
import java.util.Set;
import java.util.UUID;

/**
 * Partial-PATCH update for an envelope. All fields are nullable; service applies only non-null
 * fields (Phase 3 D-08 convention). When {@code categoryIds} is non-null the service replaces the
 * entire set (mutating in place per Pitfall 3).
 */
public record UpdateEnvelopeRequest(
    @Size(max = 100) String name,
    Set<UUID> categoryIds,
    @DecimalMin(value = "0.00", inclusive = true) BigDecimal budget,
    RolloverPolicy rolloverPolicy) {}
```

**File 4: `backend/src/main/java/com/prosperity/envelope/EnvelopeAllocationRequest.java`**

```java
package com.prosperity.envelope;

import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.NotNull;
import java.math.BigDecimal;
import java.time.YearMonth;

/** Create or update a monthly budget override for an envelope (D-08, D-10). */
public record EnvelopeAllocationRequest(
    @NotNull YearMonth month,
    @NotNull @DecimalMin(value = "0.00", inclusive = true) BigDecimal allocatedAmount) {}
```

**File 5: `backend/src/main/java/com/prosperity/envelope/EnvelopeResponse.java`**

```java
package com.prosperity.envelope;

import com.prosperity.shared.EnvelopeScope;
import com.prosperity.shared.RolloverPolicy;
import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;
import java.util.UUID;

/**
 * Envelope read DTO. All monetary fields are non-negative BigDecimals except {@code available},
 * which is signed (negative = overspent). The frontend uses {@code status} + {@code ratio}
 * directly (D-13 thresholds owned server-side).
 *
 * @param defaultBudget envelope's default monthly budget (Envelope.budget)
 * @param effectiveBudget budget actually applied this month (override if present, else default)
 * @param consumed non-negative amount spent in linked categories this month
 * @param available {@code effectiveBudget + carryOver - consumed} (signed; negative = overspent)
 * @param ratio {@code consumed / (effectiveBudget + carryOver)} (D-13 literal denominator =
 *     allocatable total for the period; >1.0 means overspent; 0.0 when allocatable &le; 0)
 * @param hasMonthlyOverride true when an EnvelopeAllocation row exists for this month
 */
public record EnvelopeResponse(
    UUID id,
    UUID bankAccountId,
    String bankAccountName,
    String name,
    EnvelopeScope scope,
    UUID ownerId,
    List<EnvelopeCategoryRef> categories,
    RolloverPolicy rolloverPolicy,
    BigDecimal defaultBudget,
    BigDecimal effectiveBudget,
    BigDecimal consumed,
    BigDecimal available,
    BigDecimal ratio,
    EnvelopeStatus status,
    boolean hasMonthlyOverride,
    boolean archived,
    Instant createdAt) {

  /** Lightweight inner record for category id+name pairs (avoids returning full Category DTO). */
  public record EnvelopeCategoryRef(UUID id, String name) {}
}
```

**File 6: `backend/src/main/java/com/prosperity/envelope/EnvelopeAllocationResponse.java`**

```java
package com.prosperity.envelope;

import java.math.BigDecimal;
import java.time.Instant;
import java.time.YearMonth;
import java.util.UUID;

/** Read DTO for a monthly budget override (D-08, D-10). */
public record EnvelopeAllocationResponse(
    UUID id, UUID envelopeId, YearMonth month, BigDecimal allocatedAmount, Instant createdAt) {}
```

**File 7: `backend/src/main/java/com/prosperity/envelope/EnvelopeHistoryEntry.java`**

```java
package com.prosperity.envelope;

import java.math.BigDecimal;
import java.time.YearMonth;

/**
 * One month's row in the 12-month consumption history (ENVL-06). {@code available} reflects
 * rollover semantics if applicable; {@code ratio} and {@code status} mirror EnvelopeResponse
 * thresholds (denominator = allocatable = effectiveBudget + carryOver, D-13).
 */
public record EnvelopeHistoryEntry(
    YearMonth month,
    BigDecimal effectiveBudget,
    BigDecimal consumed,
    BigDecimal available,
    BigDecimal ratio,
    EnvelopeStatus status) {}
```

Notes:
- All amounts are `BigDecimal` (consistent with Money.amount() and existing TransactionResponse.amount).
- `categoryIds` is `Set<UUID>` on requests (order-irrelevant) but `List<EnvelopeCategoryRef>` on the response (preserves a stable order chosen by the service for UI display).
- `EnvelopeResponse.scope`/`ownerId` are exposed read-only — the service derives both (D-07).
- `effectiveBudget` is what the UI displays; `defaultBudget` is shown only when override differs (UI-SPEC line 223 pencil icon).
- **D-13 ratio denominator** = `effectiveBudget + carryOver` (allocatable total for the period). For RESET envelopes, carryOver=0 so denominator = effectiveBudget. For CARRY_OVER envelopes with positive prev remainder, denominator includes that bonus — keeps the indicator honest about how close the user is to fully consuming everything they had available this month.
  </action>
  <verify>
    <automated>cd /home/negus/dev/prosperity && ./mvnw -pl backend compile -q 2>&1 | tail -10</automated>
  </verify>
  <acceptance_criteria>
    - All 7 files exist at the specified paths
    - `grep -c "public enum EnvelopeStatus" backend/src/main/java/com/prosperity/envelope/EnvelopeStatus.java` returns 1
    - `grep -c "GREEN" backend/src/main/java/com/prosperity/envelope/EnvelopeStatus.java` returns 1
    - `grep -c "YELLOW" backend/src/main/java/com/prosperity/envelope/EnvelopeStatus.java` returns 1
    - `grep -c "RED" backend/src/main/java/com/prosperity/envelope/EnvelopeStatus.java` returns 1
    - `grep -c "scope" backend/src/main/java/com/prosperity/envelope/CreateEnvelopeRequest.java` returns 0 (Pitfall 4: NO scope field)
    - `grep -c "Set<@NotNull UUID> categoryIds" backend/src/main/java/com/prosperity/envelope/CreateEnvelopeRequest.java` returns 1
    - `grep -c "@NotEmpty" backend/src/main/java/com/prosperity/envelope/CreateEnvelopeRequest.java` returns 1
    - `grep -c "@DecimalMin" backend/src/main/java/com/prosperity/envelope/CreateEnvelopeRequest.java` returns 1
    - `grep -c "@DecimalMin" backend/src/main/java/com/prosperity/envelope/EnvelopeAllocationRequest.java` returns 1
    - `grep -c "@NotNull" backend/src/main/java/com/prosperity/envelope/UpdateEnvelopeRequest.java` returns 0 (partial PATCH; only @Size + @DecimalMin allowed)
    - `grep -c "EnvelopeStatus status" backend/src/main/java/com/prosperity/envelope/EnvelopeResponse.java` returns 1
    - `grep -c "EnvelopeCategoryRef" backend/src/main/java/com/prosperity/envelope/EnvelopeResponse.java` returns at least 2 (declaration + field type)
    - `grep -c "YearMonth month" backend/src/main/java/com/prosperity/envelope/EnvelopeAllocationResponse.java` returns 1
    - `grep -c "YearMonth month" backend/src/main/java/com/prosperity/envelope/EnvelopeHistoryEntry.java` returns 1
    - `grep -c "effectiveBudget + carryOver" backend/src/main/java/com/prosperity/envelope/EnvelopeResponse.java` returns at least 1 (D-13 denominator documented in Javadoc)
    - `./mvnw -pl backend compile -q` exits 0
  </acceptance_criteria>
  <done>All 7 DTO/enum files exist, compile, and follow Phase 3/5 conventions; CreateEnvelopeRequest has NO scope field per Pitfall 4; EnvelopeResponse + EnvelopeStatus Javadocs document the D-13 denominator (effectiveBudget + carryOver).</done>
</task>

<task type="auto" tdd="false">
  <name>Task 2: Custom exceptions (EnvelopeNotFound, EnvelopeAllocationNotFound, DuplicateEnvelopeCategory)</name>
  <files>backend/src/main/java/com/prosperity/envelope/EnvelopeNotFoundException.java, backend/src/main/java/com/prosperity/envelope/EnvelopeAllocationNotFoundException.java, backend/src/main/java/com/prosperity/envelope/DuplicateEnvelopeCategoryException.java</files>
  <read_first>
    - backend/src/main/java/com/prosperity/account/AccountNotFoundException.java (template — single String message constructor)
    - backend/src/main/java/com/prosperity/category/DuplicateCategoryNameException.java (template for "duplicate" exceptions -> 409)
  </read_first>
  <action>
Create exactly these three files.

**File 1: `backend/src/main/java/com/prosperity/envelope/EnvelopeNotFoundException.java`**

```java
package com.prosperity.envelope;

/** Thrown when an envelope id is not found. Mapped to HTTP 404 by the controller. */
public class EnvelopeNotFoundException extends RuntimeException {

  public EnvelopeNotFoundException(String message) {
    super(message);
  }
}
```

**File 2: `backend/src/main/java/com/prosperity/envelope/EnvelopeAllocationNotFoundException.java`**

```java
package com.prosperity.envelope;

/** Thrown when an envelope allocation (monthly override) id is not found. Mapped to HTTP 404. */
public class EnvelopeAllocationNotFoundException extends RuntimeException {

  public EnvelopeAllocationNotFoundException(String message) {
    super(message);
  }
}
```

**File 3: `backend/src/main/java/com/prosperity/envelope/DuplicateEnvelopeCategoryException.java`**

```java
package com.prosperity.envelope;

/**
 * Thrown when a category is already linked to another envelope on the same account (D-01). Mapped
 * to HTTP 409 Conflict by the controller.
 */
public class DuplicateEnvelopeCategoryException extends RuntimeException {

  public DuplicateEnvelopeCategoryException(String message) {
    super(message);
  }
}
```

Do NOT add an HTTP status annotation (e.g. `@ResponseStatus`) — Plan 05 controller wires status codes via `@ExceptionHandler` (project convention from Phase 3/5).
  </action>
  <verify>
    <automated>cd /home/negus/dev/prosperity && ./mvnw -pl backend compile -q 2>&1 | tail -10</automated>
  </verify>
  <acceptance_criteria>
    - All 3 files exist at the specified paths
    - `grep -c "extends RuntimeException" backend/src/main/java/com/prosperity/envelope/EnvelopeNotFoundException.java` returns 1
    - `grep -c "extends RuntimeException" backend/src/main/java/com/prosperity/envelope/EnvelopeAllocationNotFoundException.java` returns 1
    - `grep -c "extends RuntimeException" backend/src/main/java/com/prosperity/envelope/DuplicateEnvelopeCategoryException.java` returns 1
    - `grep -c "@ResponseStatus" backend/src/main/java/com/prosperity/envelope/EnvelopeNotFoundException.java` returns 0
    - `grep -c "@ResponseStatus" backend/src/main/java/com/prosperity/envelope/DuplicateEnvelopeCategoryException.java` returns 0
    - `./mvnw -pl backend compile -q` exits 0
  </acceptance_criteria>
  <done>Three exception classes created, each extending RuntimeException with a single String constructor, no HTTP status annotation (controller wires status).</done>
</task>

</tasks>

<verification>
- `./mvnw -pl backend compile` exits 0.
- All declared DTOs and exceptions are visible to the IDE / Spring container.
- No file imports `org.springframework.web.bind.annotation.ResponseStatus` (status mapping is a controller concern in this codebase).
</verification>

<success_criteria>
- 10 new files exist in backend/src/main/java/com/prosperity/envelope (7 DTOs + 3 exceptions).
- CreateEnvelopeRequest has no scope field (Pitfall 4 enforced at the type level).
- UpdateEnvelopeRequest has only nullable fields (partial PATCH).
- EnvelopeResponse exposes status + ratio so the frontend never re-derives thresholds (D-13 single source of truth, denominator = effectiveBudget + carryOver).
- All files compile successfully.
</success_criteria>

<output>
After completion, create `.planning/phases/06-envelope-budgets/06-02-dtos-and-exceptions-SUMMARY.md`.
</output>
