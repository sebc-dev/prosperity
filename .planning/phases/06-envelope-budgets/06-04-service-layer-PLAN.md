---
phase: 06-envelope-budgets
plan: 04
type: execute
wave: 2
depends_on:
  - 06-01-data-layer-PLAN.md
  - 06-02-dtos-and-exceptions-PLAN.md
files_modified:
  - backend/src/main/java/com/prosperity/envelope/EnvelopeService.java
  - backend/src/main/java/com/prosperity/envelope/EnvelopeAllocationService.java
autonomous: true
requirements:
  - ENVL-01
  - ENVL-02
  - ENVL-03
  - ENVL-04
  - ENVL-05
  - ENVL-06
  - ENVL-07
must_haves:
  truths:
    - "EnvelopeService creates envelopes deriving scope from Account.accountType (D-07): SHARED account -> scope=SHARED, owner=null; PERSONAL account -> scope=PERSONAL, owner=current user (Pitfall 4 enforced — never trusts a client-supplied scope)"
    - "EnvelopeService validates D-01 (one category per envelope per account) on create AND on update via existsCategoryLinkOnAccount (excluding self when updating)"
    - "EnvelopeService computes consumed via repository.sumConsumedForMonth (recursive CTE, transactions + splits with NOT EXISTS dedup, half-open month interval)"
    - "EnvelopeService.computeAvailable applies rollover formula: RESET -> budget - consumed; CARRY_OVER -> budget + max(0, prevBudget - prevConsumed) - consumed (D-12, 1-month lookback, zero-clamp negative carryover)"
    - "EnvelopeService.computeRatio uses denominator = effectiveBudget + carryOver (D-13 literal: ratio = consumed / available where 'available' = the allocatable total for the period, not the signed remainder); returns 0 when allocatable<=0"
    - "EnvelopeService.computeStatus returns GREEN when ratio<0.80, YELLOW when 0.80<=ratio<=1.00, RED when ratio>1.00; defensive GREEN when allocatable<=0"
    - "EnvelopeService updates use clear()+addAll() on Envelope.categories (Pitfall 3: never reassign @ManyToMany collection)"
    - "EnvelopeService.deleteEnvelope hard-deletes when no allocations exist (repository.hasAnyAllocation false), soft-deletes (archived=true) otherwise (D-18)"
    - "EnvelopeService enforces 403 vs 404 via existsById then access check, mirroring TransactionService.requireAccountAccess"
    - "EnvelopeAllocationService CRUD overrides per envelope (D-08, D-10) and lets DataIntegrityViolationException bubble up for the controller to translate to 409"
  artifacts:
    - path: "backend/src/main/java/com/prosperity/envelope/EnvelopeService.java"
      provides: "Envelope CRUD + consumed + rollover + status (heart of Phase 6)"
      contains: "createEnvelope"
    - path: "backend/src/main/java/com/prosperity/envelope/EnvelopeAllocationService.java"
      provides: "Monthly override CRUD with access control inheritance"
      contains: "createAllocation"
  key_links:
    - from: "EnvelopeService.createEnvelope"
      to: "Account.accountType (scope derivation)"
      via: "switch(account.getAccountType())"
      pattern: "account\\.getAccountType\\(\\)"
    - from: "EnvelopeService.computeAvailable"
      to: "EnvelopeRepository.sumConsumedForMonth"
      via: "called for current month and (CARRY_OVER) previous month"
      pattern: "sumConsumedForMonth"
    - from: "EnvelopeService access control"
      to: "AccountRepository.hasAccess"
      via: "requireAccountAccess(accountId, userId, level)"
      pattern: "accountRepository\\.hasAccess"
    - from: "EnvelopeService.computeRatio"
      to: "D-13 literal denominator"
      via: "consumed.divide(effectiveBudget.add(carryOver), 4, HALF_UP)"
      pattern: "effectiveBudget\\.add\\(carryOver\\)"
---

<objective>
Build the EnvelopeService — the heart of Phase 6 — and the small EnvelopeAllocationService for monthly overrides. This plan turns the data layer (Plan 01) and DTOs (Plan 02) into working business logic: scope derivation, D-01 uniqueness enforcement, consumed aggregation, lazy rollover formula, status computation, partial-PATCH update (Pitfall 3 collection mutation), and hard/soft delete (D-18).

Purpose: The controller layer (Plan 05) will be thin — it delegates everything to these two services. Concentrating the business rules in one place keeps Phase 10 dashboard reuse trivial.

Output: Two service classes, fully implemented, exposing the methods the controllers in Plan 05 will call.
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
@.planning/phases/06-envelope-budgets/06-01-data-layer-PLAN.md
@.planning/phases/06-envelope-budgets/06-02-dtos-and-exceptions-PLAN.md

@backend/src/main/java/com/prosperity/envelope/Envelope.java
@backend/src/main/java/com/prosperity/envelope/EnvelopeAllocation.java
@backend/src/main/java/com/prosperity/envelope/EnvelopeRepository.java
@backend/src/main/java/com/prosperity/envelope/EnvelopeAllocationRepository.java
@backend/src/main/java/com/prosperity/envelope/EnvelopeStatus.java
@backend/src/main/java/com/prosperity/envelope/CreateEnvelopeRequest.java
@backend/src/main/java/com/prosperity/envelope/UpdateEnvelopeRequest.java
@backend/src/main/java/com/prosperity/envelope/EnvelopeAllocationRequest.java
@backend/src/main/java/com/prosperity/envelope/EnvelopeResponse.java
@backend/src/main/java/com/prosperity/envelope/EnvelopeAllocationResponse.java
@backend/src/main/java/com/prosperity/envelope/EnvelopeHistoryEntry.java
@backend/src/main/java/com/prosperity/envelope/EnvelopeNotFoundException.java
@backend/src/main/java/com/prosperity/envelope/DuplicateEnvelopeCategoryException.java
@backend/src/main/java/com/prosperity/transaction/TransactionService.java
@backend/src/main/java/com/prosperity/account/AccountService.java
@backend/src/main/java/com/prosperity/account/AccountRepository.java
@backend/src/main/java/com/prosperity/category/CategoryRepository.java
@backend/src/main/java/com/prosperity/auth/UserRepository.java
@backend/src/main/java/com/prosperity/shared/Money.java
@backend/src/main/java/com/prosperity/shared/AccountType.java

<revision_note>
**Iteration 1 revision (BLOCKER 1, Option A):** D-13 ratio denominator updated from `effectiveBudget` to `effectiveBudget + carryOver` (the allocatable total). This matches CONTEXT.md D-13 literal definition: ratio = consumed / available, where 'available' here means 'allocatable for the period' (not the signed remainder field — that is the post-consumption surplus/deficit). For RESET envelopes carryOver=0 so denominator collapses to effectiveBudget. For CARRY_OVER with positive prev remainder, the carryover bonus is included so the indicator honestly reflects how close the user is to fully spending what they had to spend this month. Defensive: when allocatable<=0 we return ratio=0 (drives status to GREEN). Note: the EnvelopeResponse `available` field stays defined as `effectiveBudget + carryOver - consumed` (signed) — that field is unchanged.
</revision_note>

<interfaces>
TransactionService.requireAccountAccess pattern (lines 379-388 of TransactionService.java):
```java
private void requireAccountAccess(UUID accountId, UUID userId, AccessLevel required) {
  if (!accountRepository.existsById(accountId)) {
    throw new AccountNotFoundException("Account not found: " + accountId);
  }
  if (!accountRepository.hasAccess(accountId, userId, AccessLevel.allAtLeast(required))) {
    throw new AccountAccessDeniedException("Access denied to account: " + accountId);
  }
}
```
NOTE: AccessLevel does not have an `allAtLeast` static — see TransactionService for the actual collection (it uses Arrays.asList(AccessLevel.values()) filtered). Use the SAME helper / pattern: `Arrays.stream(AccessLevel.values()).filter(l -> l.isAtLeast(required)).toList()`.

User resolution pattern (TransactionService.resolveUser):
```java
User user = userRepository.findByEmail(userEmail)
    .orElseThrow(() -> new UserNotFoundException("User not found: " + userEmail));
```

CategoryRepository — has findById(UUID) returning Optional<Category>; Category has getName() and getParent() (nullable).

EnvelopeRepository methods available (from Plan 01):
- findByAccountAccessibleToUser(accountId, userId) -> List<Envelope>
- findAllAccessibleToUser(userId) -> List<Envelope>
- findAllAccessibleToUserIncludingArchived(userId) -> List<Envelope>
- existsCategoryLinkOnAccount(accountId, categoryId, envelopeIdToExclude) -> boolean
- sumConsumedForMonth(envelopeId, accountId, monthStart, nextMonthStart) -> BigDecimal
- findMonthlyConsumptionRange(envelopeId, accountId, from, to) -> List<Object[]> (each row [LocalDate month_start, BigDecimal consumed])
- hasAnyAllocation(envelopeId) -> boolean

EnvelopeAllocationRepository methods available (from Plan 01):
- findByEnvelopeIdAndMonthValue(envelopeId, monthStart) -> Optional<EnvelopeAllocation>
- findByEnvelopeIdAndMonthRange(envelopeId, from, to) -> List<EnvelopeAllocation>
- findByEnvelopeIdOrderByMonthValueAsc(envelopeId) -> List<EnvelopeAllocation>
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: EnvelopeService — CRUD + scope derivation + D-01 + consumed + rollover + status + history + soft delete</name>
  <files>backend/src/main/java/com/prosperity/envelope/EnvelopeService.java</files>
  <note>This task implements ~16 methods across one ~400 line class. If context budget tightens during execution, commit after each logical group: (a) helpers + scaffolding, (b) CRUD methods, (c) rollover/ratio/status math, (d) history. Read_first list is intentional — load it before starting so you don't need to re-explore mid-task.</note>
  <read_first>
    - backend/src/main/java/com/prosperity/transaction/TransactionService.java (canonical access-check pattern requireAccountAccess + resolveUser; mirror exactly for envelopes)
    - backend/src/main/java/com/prosperity/account/AccountService.java (existsById then access check pattern, hard delete vs soft via flag)
    - backend/src/main/java/com/prosperity/envelope/EnvelopeRepository.java (Plan 01 output — methods available)
    - backend/src/main/java/com/prosperity/envelope/EnvelopeAllocationRepository.java (Plan 01 output)
    - backend/src/main/java/com/prosperity/envelope/Envelope.java (Plan 01 output — categories Set + archived flag)
    - backend/src/main/java/com/prosperity/category/Category.java (getParent / getChildren — confirm names)
    - backend/src/main/java/com/prosperity/shared/Money.java (BigDecimal-based value object with amount(), zero(), add, subtract)
    - backend/src/main/java/com/prosperity/shared/AccountType.java (PERSONAL, SHARED enum values)
    - backend/src/test/java/com/prosperity/envelope/EnvelopeServiceTest.java (test names tell you the contract — names are the spec)
  </read_first>
  <behavior>
    - createEnvelope on PERSONAL account: scope=PERSONAL, owner=current user; ignores any client-supplied scope
    - createEnvelope on SHARED account: scope=SHARED, owner=null; ignores any client-supplied scope
    - createEnvelope without WRITE access on the account: throws AccountAccessDeniedException
    - createEnvelope on nonexistent account: throws AccountNotFoundException (404 before 403 per existsById check)
    - createEnvelope referencing a category already linked to ANOTHER non-archived envelope on the same account: throws DuplicateEnvelopeCategoryException
    - createEnvelope referencing a category that is unknown: throws CategoryNotFoundException
    - listEnvelopes by account returns only envelopes accessible to user, archived excluded by default
    - listEnvelopes(includeArchived=true) returns archived envelopes too
    - getEnvelope returns full EnvelopeResponse with consumed/available/ratio/status for current month
    - getEnvelope without READ access -> AccountAccessDeniedException; nonexistent envelope -> EnvelopeNotFoundException
    - updateEnvelope (partial PATCH): name/budget/rolloverPolicy applied only when non-null; categoryIds when non-null replaces categories via clear()+addAll() (Pitfall 3); D-01 re-validated excluding self; WRITE required
    - deleteEnvelope with no allocations: hard-delete (envelopeRepository.delete)
    - deleteEnvelope with allocations: soft-delete (set archived=true)
    - getEnvelopeHistory(id, fromMonth, toMonth) returns 12-month list aligned with EnvelopeHistoryEntry (effectiveBudget overlay from allocations + consumed bucket from repository)
    - computeStatus: ratio<0.80 GREEN, 0.80<=ratio<=1.00 YELLOW, ratio>1.00 RED, allocatable<=0 GREEN (defensive)
    - computeAvailable RESET: budget - consumed (no carryOver)
    - computeAvailable CARRY_OVER positive prev remainder: budget + (prevBudget - prevConsumed) - consumed
    - computeAvailable CARRY_OVER negative prev remainder: clamped to 0 carryOver -> budget - consumed
    - computeAvailable CARRY_OVER lookback exactly 1 month (does not chain back further)
    - computeRatio: denominator = effectiveBudget + carryOver (D-13 literal); returns 0 when allocatable<=0
  </behavior>
  <action>
Create `backend/src/main/java/com/prosperity/envelope/EnvelopeService.java` exactly per the contract below. Use the EXACT method signatures listed; the controller in Plan 05 will call these names.

**Class skeleton + dependencies:**

```java
package com.prosperity.envelope;

import com.prosperity.account.AccessLevel;
import com.prosperity.account.Account;
import com.prosperity.account.AccountAccessDeniedException;
import com.prosperity.account.AccountNotFoundException;
import com.prosperity.account.AccountRepository;
import com.prosperity.auth.User;
import com.prosperity.auth.UserNotFoundException;
import com.prosperity.auth.UserRepository;
import com.prosperity.category.Category;
import com.prosperity.category.CategoryNotFoundException;
import com.prosperity.category.CategoryRepository;
import com.prosperity.shared.AccountType;
import com.prosperity.shared.EnvelopeScope;
import com.prosperity.shared.Money;
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.time.LocalDate;
import java.time.YearMonth;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collection;
import java.util.Comparator;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.Set;
import java.util.UUID;
import java.util.stream.Collectors;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class EnvelopeService {

  private static final BigDecimal YELLOW_THRESHOLD = new BigDecimal("0.80");
  private static final BigDecimal RED_THRESHOLD = new BigDecimal("1.00");

  private final EnvelopeRepository envelopeRepository;
  private final EnvelopeAllocationRepository allocationRepository;
  private final AccountRepository accountRepository;
  private final CategoryRepository categoryRepository;
  private final UserRepository userRepository;

  public EnvelopeService(
      EnvelopeRepository envelopeRepository,
      EnvelopeAllocationRepository allocationRepository,
      AccountRepository accountRepository,
      CategoryRepository categoryRepository,
      UserRepository userRepository) {
    this.envelopeRepository = envelopeRepository;
    this.allocationRepository = allocationRepository;
    this.accountRepository = accountRepository;
    this.categoryRepository = categoryRepository;
    this.userRepository = userRepository;
  }

  // ---------------- Public API -----------------------------------------

  @Transactional
  public EnvelopeResponse createEnvelope(UUID accountId, CreateEnvelopeRequest request, String userEmail);

  @Transactional(readOnly = true)
  public List<EnvelopeResponse> listEnvelopesForAccount(UUID accountId, boolean includeArchived, String userEmail);

  @Transactional(readOnly = true)
  public List<EnvelopeResponse> listAllEnvelopes(boolean includeArchived, String userEmail);

  @Transactional(readOnly = true)
  public EnvelopeResponse getEnvelope(UUID envelopeId, String userEmail);

  @Transactional
  public EnvelopeResponse updateEnvelope(UUID envelopeId, UpdateEnvelopeRequest request, String userEmail);

  /** Hard-deletes when no EnvelopeAllocation exists, otherwise sets archived=true (D-18). */
  @Transactional
  public void deleteEnvelope(UUID envelopeId, String userEmail);

  /** Returns 12-month history ending at {@code monthInclusive} (i.e. months [monthInclusive-11, monthInclusive]). */
  @Transactional(readOnly = true)
  public List<EnvelopeHistoryEntry> getEnvelopeHistory(UUID envelopeId, YearMonth monthInclusive, String userEmail);
}
```

**Implementation requirements (be exact):**

1. **`requireAccountAccess(UUID accountId, UUID userId, AccessLevel required)`** (private helper):
   ```java
   if (!accountRepository.existsById(accountId)) {
     throw new AccountNotFoundException("Account not found: " + accountId);
   }
   List<AccessLevel> levels = Arrays.stream(AccessLevel.values())
       .filter(l -> l.isAtLeast(required))
       .toList();
   if (!accountRepository.hasAccess(accountId, userId, levels)) {
     throw new AccountAccessDeniedException("Access denied to account: " + accountId);
   }
   ```

2. **`requireEnvelopeAccess(UUID envelopeId, UUID userId, AccessLevel required) -> Envelope`** (private helper that loads the envelope while enforcing 403 vs 404):
   - if `!envelopeRepository.existsById(envelopeId)` -> throw `EnvelopeNotFoundException`
   - load `Envelope env = envelopeRepository.findById(envelopeId).orElseThrow(...)`
   - call `requireAccountAccess(env.getBankAccount().getId(), userId, required)`
   - return env

3. **`createEnvelope`**:
   - resolveUser by email
   - requireAccountAccess(accountId, user.id, WRITE)
   - load `Account account = accountRepository.findById(accountId).orElseThrow(AccountNotFoundException::new)`
   - load Category entities via `categoryRepository.findAllById(request.categoryIds())` — if size mismatch, throw `CategoryNotFoundException` listing the missing ids
   - validate D-01 for EACH categoryId: if `envelopeRepository.existsCategoryLinkOnAccount(accountId, categoryId, null)` -> throw `DuplicateEnvelopeCategoryException("La categorie " + categoryId + " est deja liee a une autre enveloppe de ce compte")`
   - derive scope+owner: `scope = account.getAccountType() == AccountType.SHARED ? EnvelopeScope.SHARED : EnvelopeScope.PERSONAL` ; `owner = scope == EnvelopeScope.PERSONAL ? user : null`
   - construct `new Envelope(account, request.name(), scope, new Money(request.budget()))`, then `setOwner(owner)`, `setRolloverPolicy(request.rolloverPolicy())`, `getCategories().addAll(loadedCategories)`
   - `envelopeRepository.save(env)`
   - return `toResponse(env, YearMonth.now())`

4. **`updateEnvelope`** (partial PATCH per Phase 3 D-08):
   - resolveUser
   - load env via `requireEnvelopeAccess(envelopeId, user.id, WRITE)`
   - if `request.name() != null` -> `env.setName(request.name())`
   - if `request.budget() != null` -> `env.setBudget(new Money(request.budget()))`
   - if `request.rolloverPolicy() != null` -> `env.setRolloverPolicy(request.rolloverPolicy())`
   - if `request.categoryIds() != null`:
     - load categories with findAllById; size mismatch -> CategoryNotFoundException
     - validate D-01 each categoryId with `envelopeRepository.existsCategoryLinkOnAccount(accountId, catId, envelopeId)` (note: pass envelopeId-to-exclude so the envelope being edited is allowed to keep its categories)
     - **CRITICAL Pitfall 3:** mutate in place: `env.getCategories().clear(); env.getCategories().addAll(loadedCategories);` — DO NOT call `env.setCategories(newSet)`
   - `envelopeRepository.save(env)` (idempotent, but explicit for clarity)
   - return `toResponse(env, YearMonth.now())`

5. **`deleteEnvelope`** (D-18 hard vs soft):
   - resolveUser
   - load via `requireEnvelopeAccess(envelopeId, user.id, WRITE)`
   - if `envelopeRepository.hasAnyAllocation(envelopeId)`:
     - `env.setArchived(true); envelopeRepository.save(env);`
   - else:
     - `envelopeRepository.delete(env);`

6. **`listEnvelopesForAccount(accountId, includeArchived, userEmail)`**:
   - resolveUser
   - requireAccountAccess(accountId, user.id, READ)
   - if includeArchived: load via dedicated repo method (or filter); else `findByAccountAccessibleToUser`
   - For each envelope: `toResponse(env, YearMonth.now())`
   - Implementation note: `findByAccountAccessibleToUser` already filters archived=false. For `includeArchived=true` on a single account, add an inline JPQL or use `findAllAccessibleToUserIncludingArchived(userId)` then filter by accountId in Java. Simplest: Java-side filter on the IncludingArchived list. (Acceptable: list scale is small per D-22.)

7. **`listAllEnvelopes(includeArchived, userEmail)`** — uses `findAllAccessibleToUser` or `findAllAccessibleToUserIncludingArchived`.

8. **`getEnvelope(envelopeId, userEmail)`**:
   - resolveUser
   - load via `requireEnvelopeAccess(envelopeId, user.id, READ)`
   - return `toResponse(env, YearMonth.now())`

9. **`getEnvelopeHistory(envelopeId, monthInclusive, userEmail)`**:
   - resolveUser
   - load env via `requireEnvelopeAccess(envelopeId, user.id, READ)`
   - `YearMonth from = monthInclusive.minusMonths(11);`
   - `LocalDate fromDate = from.atDay(1);`
   - `LocalDate toDate = monthInclusive.plusMonths(1).atDay(1);` // exclusive bound
   - load consumption rows: `List<Object[]> rows = envelopeRepository.findMonthlyConsumptionRange(envelopeId, env.getBankAccount().getId(), fromDate, toDate);`
   - load allocation overrides: `List<EnvelopeAllocation> overrides = allocationRepository.findByEnvelopeIdAndMonthRange(envelopeId, fromDate, toDate);`
   - build `Map<YearMonth, BigDecimal> overrideByMonth` from overrides
   - build `Map<YearMonth, BigDecimal> consumedByMonth` from rows (row[0] is `java.sql.Date` or LocalDate — use `((java.sql.Date) row[0]).toLocalDate()` if Date, or cast directly to LocalDate; both work depending on PostgreSQL JDBC driver; safest: `LocalDate ld = ((java.sql.Date) row[0]).toLocalDate();`)
   - For each YearMonth from `from` to `monthInclusive` (inclusive, 12 entries):
     - `BigDecimal effective = overrideByMonth.getOrDefault(ym, env.getBudget().amount());`
     - `BigDecimal consumed = consumedByMonth.getOrDefault(ym, BigDecimal.ZERO);`
     - `Money available = computeAvailable(env, ym);` // reuse same formula
     - `BigDecimal carry = computeCarryOver(env, ym);` // private helper, see step 11b below
     - `BigDecimal allocatable = effective.add(carry);`
     - `BigDecimal ratio = computeRatio(consumed, allocatable);`
     - `EnvelopeStatus status = computeStatus(ratio);`
     - add `new EnvelopeHistoryEntry(ym, effective, consumed, available.amount(), ratio, status)`
   - return list ordered ascending by month

10. **`computeAvailable(Envelope env, YearMonth month) -> Money`** (private):
    ```java
    BigDecimal effectiveBudget = resolveEffectiveBudget(env, month).amount();
    BigDecimal consumed = sumConsumed(env, month).amount();
    BigDecimal carryOver = computeCarryOver(env, month);
    return new Money(effectiveBudget.add(carryOver).subtract(consumed));
    ```
    NOTE: 1-month lookback only — recursion does NOT chain to prev-prev (D-12 v1 lock).

11a. **`computeCarryOver(Envelope env, YearMonth month) -> BigDecimal`** (private — extracted so both `computeAvailable` and `computeRatio` use the same value):
    ```java
    if (env.getRolloverPolicy() != RolloverPolicy.CARRY_OVER) {
      return BigDecimal.ZERO;
    }
    YearMonth prev = month.minusMonths(1);
    BigDecimal prevBudget = resolveEffectiveBudget(env, prev).amount();
    BigDecimal prevConsumed = sumConsumed(env, prev).amount();
    BigDecimal raw = prevBudget.subtract(prevConsumed);
    return raw.signum() > 0 ? raw : BigDecimal.ZERO; // zero-clamp negative (D-12 v1)
    ```

11b. **`resolveEffectiveBudget(Envelope env, YearMonth month) -> Money`** (private):
    ```java
    return allocationRepository.findByEnvelopeIdAndMonthValue(env.getId(), month.atDay(1))
        .map(EnvelopeAllocation::getAllocatedAmount)
        .orElse(env.getBudget());
    ```

12. **`sumConsumed(Envelope env, YearMonth month) -> Money`** (private):
    ```java
    LocalDate start = month.atDay(1);
    LocalDate next = month.plusMonths(1).atDay(1);
    BigDecimal raw = envelopeRepository.sumConsumedForMonth(
        env.getId(), env.getBankAccount().getId(), start, next);
    return new Money(raw == null ? BigDecimal.ZERO : raw);
    ```

13. **`computeStatus(BigDecimal ratio) -> EnvelopeStatus`** (private):
    ```java
    if (ratio == null || ratio.signum() < 0) return EnvelopeStatus.GREEN; // defensive
    if (ratio.compareTo(RED_THRESHOLD) > 0) return EnvelopeStatus.RED;
    if (ratio.compareTo(YELLOW_THRESHOLD) >= 0) return EnvelopeStatus.YELLOW;
    return EnvelopeStatus.GREEN;
    ```

14. **`computeRatio(BigDecimal consumed, BigDecimal allocatable) -> BigDecimal`** (private — D-13 literal denominator):
    - **D-13:** ratio = consumed / available, where 'available' = the allocatable total for the period = `effectiveBudget + carryOver`.
    - If `allocatable == null || allocatable.signum() <= 0` -> return `BigDecimal.ZERO` (defensive — also drives status to GREEN).
    - else `consumed.divide(allocatable, 4, RoundingMode.HALF_UP)`
    - **NOTE:** In `toResponse` and `getEnvelopeHistory`, callers pass `effectiveBudget.add(carryOver)` as the allocatable argument. Do NOT pass just `effectiveBudget` — that diverges from D-13 when rollover is active.

15. **`toResponse(Envelope env, YearMonth currentMonth) -> EnvelopeResponse`** (private):
    ```java
    Money effectiveBudget = resolveEffectiveBudget(env, currentMonth);
    boolean hasOverride = allocationRepository
        .findByEnvelopeIdAndMonthValue(env.getId(), currentMonth.atDay(1)).isPresent();
    Money consumed = sumConsumed(env, currentMonth);
    BigDecimal carryOver = computeCarryOver(env, currentMonth);
    BigDecimal allocatable = effectiveBudget.amount().add(carryOver);
    Money available = new Money(allocatable.subtract(consumed.amount())); // = effective + carry - consumed
    BigDecimal ratio = computeRatio(consumed.amount(), allocatable);
    EnvelopeStatus status = computeStatus(ratio);
    List<EnvelopeResponse.EnvelopeCategoryRef> cats = env.getCategories().stream()
        .sorted(Comparator.comparing(Category::getName))
        .map(c -> new EnvelopeResponse.EnvelopeCategoryRef(c.getId(), c.getName()))
        .toList();
    return new EnvelopeResponse(
        env.getId(),
        env.getBankAccount().getId(),
        env.getBankAccount().getName(),
        env.getName(),
        env.getScope(),
        env.getOwner() == null ? null : env.getOwner().getId(),
        cats,
        env.getRolloverPolicy(),
        env.getBudget().amount(),
        effectiveBudget.amount(),
        consumed.amount(),
        available.amount(),
        ratio,
        status,
        hasOverride,
        env.isArchived(),
        env.getCreatedAt());
    ```
    **D-13 reminder:** the `available` field returned to the client is signed (allocatable - consumed); the `ratio` field uses the unsigned allocatable as denominator. Both align with D-13 because D-13 says "ratio = consumed / available" using "available" in the sense of "how much was allocatable to spend", not "what's left after spending".

16. **`resolveUser(String userEmail) -> User`** (private):
    ```java
    return userRepository.findByEmail(userEmail)
        .orElseThrow(() -> new UserNotFoundException("User not found: " + userEmail));
    ```

Add `@Transactional` on every public method (readOnly=true on getters/listers, default on mutators). Document Javadoc on each public method including which exceptions can be thrown.
  </action>
  <verify>
    <automated>cd /home/negus/dev/prosperity && ./mvnw -pl backend compile -q 2>&1 | tail -10 && ./mvnw -pl backend test -Dtest=EnvelopeTest -q 2>&1 | tail -5</automated>
  </verify>
  <acceptance_criteria>
    - File `backend/src/main/java/com/prosperity/envelope/EnvelopeService.java` exists
    - `grep -c "@Service" backend/src/main/java/com/prosperity/envelope/EnvelopeService.java` returns 1
    - `grep -c "public EnvelopeResponse createEnvelope" backend/src/main/java/com/prosperity/envelope/EnvelopeService.java` returns 1
    - `grep -c "public EnvelopeResponse updateEnvelope" backend/src/main/java/com/prosperity/envelope/EnvelopeService.java` returns 1
    - `grep -c "public void deleteEnvelope" backend/src/main/java/com/prosperity/envelope/EnvelopeService.java` returns 1
    - `grep -c "public List<EnvelopeResponse> listEnvelopesForAccount" backend/src/main/java/com/prosperity/envelope/EnvelopeService.java` returns 1
    - `grep -c "public List<EnvelopeResponse> listAllEnvelopes" backend/src/main/java/com/prosperity/envelope/EnvelopeService.java` returns 1
    - `grep -c "public EnvelopeResponse getEnvelope" backend/src/main/java/com/prosperity/envelope/EnvelopeService.java` returns 1
    - `grep -c "public List<EnvelopeHistoryEntry> getEnvelopeHistory" backend/src/main/java/com/prosperity/envelope/EnvelopeService.java` returns 1
    - `grep -c "DuplicateEnvelopeCategoryException" backend/src/main/java/com/prosperity/envelope/EnvelopeService.java` returns at least 1 (thrown in createEnvelope and updateEnvelope)
    - `grep -c "getCategories().clear()" backend/src/main/java/com/prosperity/envelope/EnvelopeService.java` returns 1 (Pitfall 3 enforced)
    - `grep -c "AccountType.SHARED" backend/src/main/java/com/prosperity/envelope/EnvelopeService.java` returns 1 (scope derivation)
    - `grep -c "EnvelopeScope.SHARED" backend/src/main/java/com/prosperity/envelope/EnvelopeService.java` returns 1
    - `grep -c "EnvelopeScope.PERSONAL" backend/src/main/java/com/prosperity/envelope/EnvelopeService.java` returns 1
    - `grep -c "hasAnyAllocation" backend/src/main/java/com/prosperity/envelope/EnvelopeService.java` returns 1 (D-18 branch)
    - `grep -c "sumConsumedForMonth" backend/src/main/java/com/prosperity/envelope/EnvelopeService.java` returns 1
    - `grep -c "RolloverPolicy.CARRY_OVER" backend/src/main/java/com/prosperity/envelope/EnvelopeService.java` returns 1
    - `grep -c "0.80" backend/src/main/java/com/prosperity/envelope/EnvelopeService.java` returns 1 (YELLOW threshold)
    - `grep -c "1.00" backend/src/main/java/com/prosperity/envelope/EnvelopeService.java` returns 1 (RED threshold)
    - `grep -c "computeCarryOver" backend/src/main/java/com/prosperity/envelope/EnvelopeService.java` returns at least 3 (declaration + computeAvailable + toResponse + history)
    - `grep -c "effectiveBudget.amount().add(carryOver)\\|allocatable" backend/src/main/java/com/prosperity/envelope/EnvelopeService.java` returns at least 1 (D-13 ratio uses allocatable, not effective alone)
    - `grep -c "@Transactional" backend/src/main/java/com/prosperity/envelope/EnvelopeService.java` returns at least 7 (one per public method)
    - `./mvnw -pl backend compile` exits 0
    - `./mvnw -pl backend test -Dtest=EnvelopeTest` exits 0 (existing entity tests still green)
  </acceptance_criteria>
  <done>EnvelopeService compiles, exposes the 7 public methods with the exact signatures, scope derivation respects D-07, D-01 enforced via existsCategoryLinkOnAccount on create AND update, Pitfall 3 collection mutation pattern in place for category replacement, soft-vs-hard delete branches on hasAnyAllocation, status thresholds match D-13, rollover formula respects D-12 (1-month lookback + zero-clamp), ratio denominator = effectiveBudget + carryOver per D-13 literal definition.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: EnvelopeAllocationService — monthly override CRUD with access inheritance</name>
  <files>backend/src/main/java/com/prosperity/envelope/EnvelopeAllocationService.java</files>
  <read_first>
    - backend/src/main/java/com/prosperity/envelope/EnvelopeService.java (Task 1 output — reuse `requireEnvelopeAccess` helper pattern; this service depends on EnvelopeService access checks)
    - backend/src/main/java/com/prosperity/envelope/EnvelopeAllocationRepository.java (Plan 01 output — methods available)
    - backend/src/main/java/com/prosperity/transaction/TransactionService.java (transactional boundaries, exception throwing style)
  </read_first>
  <behavior>
    - createAllocation requires WRITE on the envelope's account; persists EnvelopeAllocation; on duplicate (envelope+month UNIQUE constraint) lets DataIntegrityViolationException bubble up for the controller to translate to 409
    - listAllocations requires READ; returns overrides ordered by month asc
    - updateAllocation (by allocation id) requires WRITE on the envelope's account; replaces allocatedAmount only; month is immutable on update (changing month = delete + create)
    - deleteAllocation requires WRITE; throws EnvelopeAllocationNotFoundException if id unknown
  </behavior>
  <action>
Create `backend/src/main/java/com/prosperity/envelope/EnvelopeAllocationService.java`:

```java
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
import java.util.stream.Collectors;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/** Service for managing monthly budget overrides on envelopes (D-08, D-10). */
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

  /** Throws DataIntegrityViolationException on duplicate (envelope, month) — controller maps to 409. */
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

  @Transactional(readOnly = true)
  public List<EnvelopeAllocationResponse> listAllocations(UUID envelopeId, String userEmail) {
    User user = resolveUser(userEmail);
    requireEnvelopeAccess(envelopeId, user.getId(), AccessLevel.READ);
    return allocationRepository.findByEnvelopeIdOrderByMonthValueAsc(envelopeId).stream()
        .map(this::toResponse)
        .toList();
  }

  /** Replaces allocatedAmount on an existing allocation. Month is immutable here. */
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

  // --------- Helpers (duplicated from EnvelopeService for service isolation) ---------

  private Envelope requireEnvelopeAccess(UUID envelopeId, UUID userId, AccessLevel required) {
    if (!envelopeRepository.existsById(envelopeId)) {
      throw new EnvelopeNotFoundException("Envelope not found: " + envelopeId);
    }
    Envelope env =
        envelopeRepository
            .findById(envelopeId)
            .orElseThrow(() -> new EnvelopeNotFoundException("Envelope not found: " + envelopeId));
    UUID accountId = env.getBankAccount().getId();
    if (!accountRepository.existsById(accountId)) {
      throw new AccountNotFoundException("Account not found: " + accountId);
    }
    List<AccessLevel> levels =
        Arrays.stream(AccessLevel.values()).filter(l -> l.isAtLeast(required)).toList();
    if (!accountRepository.hasAccess(accountId, userId, levels)) {
      throw new AccountAccessDeniedException("Access denied to account: " + accountId);
    }
    return env;
  }

  private User resolveUser(String userEmail) {
    return userRepository
        .findByEmail(userEmail)
        .orElseThrow(() -> new UserNotFoundException("User not found: " + userEmail));
  }

  private EnvelopeAllocationResponse toResponse(EnvelopeAllocation a) {
    return new EnvelopeAllocationResponse(
        a.getId(),
        a.getEnvelope().getId(),
        a.getMonth(),
        a.getAllocatedAmount().amount(),
        a.getCreatedAt());
  }
}
```

Notes:
- The duplicate `requireEnvelopeAccess` helper is intentional — duplication beats premature abstraction across services. If a third service needs the same logic in a future phase, extract to a `EnvelopeAccessGuard` then.
- Do NOT catch `DataIntegrityViolationException` here — let it propagate so the controller's `@ExceptionHandler` translates it to 409.
  </action>
  <verify>
    <automated>cd /home/negus/dev/prosperity && ./mvnw -pl backend compile -q 2>&1 | tail -10</automated>
  </verify>
  <acceptance_criteria>
    - File `backend/src/main/java/com/prosperity/envelope/EnvelopeAllocationService.java` exists
    - `grep -c "@Service" backend/src/main/java/com/prosperity/envelope/EnvelopeAllocationService.java` returns 1
    - `grep -c "public EnvelopeAllocationResponse createAllocation" backend/src/main/java/com/prosperity/envelope/EnvelopeAllocationService.java` returns 1
    - `grep -c "public List<EnvelopeAllocationResponse> listAllocations" backend/src/main/java/com/prosperity/envelope/EnvelopeAllocationService.java` returns 1
    - `grep -c "public EnvelopeAllocationResponse updateAllocation" backend/src/main/java/com/prosperity/envelope/EnvelopeAllocationService.java` returns 1
    - `grep -c "public void deleteAllocation" backend/src/main/java/com/prosperity/envelope/EnvelopeAllocationService.java` returns 1
    - `grep -c "EnvelopeAllocationNotFoundException" backend/src/main/java/com/prosperity/envelope/EnvelopeAllocationService.java` returns at least 2 (update + delete)
    - `grep -c "@Transactional" backend/src/main/java/com/prosperity/envelope/EnvelopeAllocationService.java` returns at least 4
    - `grep -c "catch.*DataIntegrityViolationException" backend/src/main/java/com/prosperity/envelope/EnvelopeAllocationService.java` returns 0 (let bubble up)
    - `./mvnw -pl backend compile -q` exits 0
  </acceptance_criteria>
  <done>EnvelopeAllocationService compiles; exposes 4 public methods; access checks reuse the EnvelopeAccess pattern; 404 vs 403 enforced via existsById; DataIntegrityViolationException not caught (controller translates).</done>
</task>

</tasks>

<verification>
- `./mvnw -pl backend compile` exits 0.
- `./mvnw -pl backend test -Dtest='EnvelopeTest'` exits 0 (existing pure-domain tests untouched).
- `./mvnw -pl backend test -Dtest='Envelope*Test'` shows new test stubs from Plan 03 still skipped (assertions filled in Plan 06), no compile errors.
</verification>

<success_criteria>
- EnvelopeService implements all 7 public methods with exact signatures consumed by Plan 05 controllers.
- D-01 enforced on create AND update.
- D-07 scope derivation in place; CreateEnvelopeRequest never carries scope from client (Pitfall 4 doubly enforced — by DTO type and by service ignoring any value).
- D-12 rollover formula: RESET = budget - consumed; CARRY_OVER = budget + max(0, prevBudget - prevConsumed) - consumed; lookback exactly 1 month.
- D-13 status thresholds wired in computeStatus; **ratio denominator = effectiveBudget + carryOver (allocatable total), not effectiveBudget alone — single source of truth for the indicator**.
- D-18 hard-vs-soft delete branches on hasAnyAllocation.
- Pitfall 3 collection mutation (clear+addAll) used for category replacement.
- EnvelopeAllocationService implements 4 public methods.
- All files compile.
</success_criteria>

<output>
After completion, create `.planning/phases/06-envelope-budgets/06-04-service-layer-SUMMARY.md`.
</output>
