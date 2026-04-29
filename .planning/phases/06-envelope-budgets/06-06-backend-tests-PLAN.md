---
phase: 06-envelope-budgets
plan: 06
type: execute
wave: 3
depends_on:
  - 06-03-test-scaffolds-PLAN.md
  - 06-04-service-layer-PLAN.md
  - 06-05-controllers-PLAN.md
files_modified:
  - backend/src/test/java/com/prosperity/envelope/EnvelopeServiceTest.java
  - backend/src/test/java/com/prosperity/envelope/EnvelopeControllerTest.java
  - backend/src/test/java/com/prosperity/envelope/EnvelopeAllocationControllerTest.java
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
    - "All Wave 0 stub methods (Plan 03) have @Disabled removed and a real AAA body"
    - "EnvelopeServiceTest covers consumed aggregation (negative tx + splits + child categories + month boundaries + D-04 ignored), rollover formula (RESET, CARRY_OVER positive, CARRY_OVER negative clamps to zero, lookback limited to 1 month), status thresholds (boundary 80% / 100%, defensive zero budget), scope derivation (PERSONAL vs SHARED), D-01 uniqueness allowing same-category-on-different-account"
    - "EnvelopeControllerTest covers create returns 201/403/404/409, list filters by access + archived, get returns enriched response, update partial-PATCH, delete hard vs soft, history returns 12 ordered months including zero-consumed"
    - "EnvelopeAllocationControllerTest covers create (201, 403, 404, 409 duplicate month), list ordered, update replaces amount, delete returns 204"
    - "Tests follow testing-principles.md: AAA with one Act line, snake_case names, no over-mocking (use real Testcontainers PostgreSQL)"
  artifacts:
    - path: "backend/src/test/java/com/prosperity/envelope/EnvelopeServiceTest.java"
      provides: "Filled service tests"
      contains: "Arrange"
    - path: "backend/src/test/java/com/prosperity/envelope/EnvelopeControllerTest.java"
      provides: "Filled controller integration tests"
      contains: "MockMvc"
    - path: "backend/src/test/java/com/prosperity/envelope/EnvelopeAllocationControllerTest.java"
      provides: "Filled allocation controller tests"
      contains: "MockMvc"
  key_links:
    - from: "EnvelopeControllerTest"
      to: "Real PostgreSQL via Testcontainers"
      via: "@Import(TestcontainersConfig.class)"
      pattern: "@Import\\(TestcontainersConfig\\.class\\)"
    - from: "EnvelopeServiceTest"
      to: "Pitfall 7 boundary cases"
      via: "transaction_on_last_day_of_month_included + transaction_on_first_day_of_next_month_excluded"
      pattern: "transaction_on_last_day"
---

<objective>
Replace every `@Disabled("Wave 0 stub — body in Plan 06")` with a working AAA body. The stub names are the spec — each name describes scenario and expected result; the body must verify exactly that.

Use real PostgreSQL (Testcontainers) — no mocking of the data layer. Mock only what testing-principles.md allows (out-of-process, owned-by-us — none in this phase).

Purpose: Lock in Phase 6 behaviour with deterministic regression coverage. The full backend suite must be green before Plan 07/08 frontend work begins (Plan 07 depends on Plan 05 only, but Plan 06 surfaces any backend bug that the frontend would otherwise hit at runtime).

Output: 3 fully implemented backend test files; ./mvnw verify exits 0.
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
@.planning/phases/06-envelope-budgets/06-VALIDATION.md
@.claude/rules/testing-principles.md

@backend/src/test/java/com/prosperity/transaction/TransactionControllerTest.java
@backend/src/test/java/com/prosperity/envelope/EnvelopeTest.java
@backend/src/main/java/com/prosperity/envelope/EnvelopeService.java
@backend/src/main/java/com/prosperity/envelope/EnvelopeAllocationService.java
@backend/src/main/java/com/prosperity/envelope/EnvelopeController.java
@backend/src/main/java/com/prosperity/envelope/EnvelopeAllocationController.java
@backend/src/main/java/com/prosperity/envelope/EnvelopeRepository.java
@backend/src/main/java/com/prosperity/envelope/EnvelopeAllocationRepository.java

<interfaces>
TransactionControllerTest provides the canonical setup pattern:
```java
@BeforeEach
void setUp() {
  testUser = userRepository.save(new User("test@test.com", "{bcrypt}$2a$10$hash", "Test User"));
  testAccount = accountRepository.save(new Account("Compte Courant", AccountType.PERSONAL));
  accountAccessRepository.save(new AccountAccess(testUser, testAccount, AccessLevel.WRITE));
  testCategory = categoryRepository.findById(UUID.fromString("a0000000-0000-0000-0000-000000000101")).orElseThrow();
}
```

Seeded categories from V011 (deterministic UUIDs):
- a0000000-0000-0000-0000-00000000XXYY pattern (Phase 4 D-04)
- Use `a0000000-0000-0000-0000-000000000101` for a known leaf (Courses) — same as TransactionControllerTest

Test data builder approach: each test creates its own envelope via `envelopeRepository.save(...)` or via `envelopeService.createEnvelope(...)`. NO shared mutable state across tests (DirtiesContext.AFTER_EACH_TEST_METHOD enforces this).

Money construction in tests: `new Money(new BigDecimal("100.00"))` or `Money.of("100.00")`.

Transaction creation in tests: `new Transaction(account, new Money(new BigDecimal("-45.30")), LocalDate.of(2026, 4, 7), TransactionSource.MANUAL)` then setCategory + save.

For frontend test stubs (envelopes.spec.ts etc): they are created in Plan 08 alongside the components — NOT here.
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Fill EnvelopeServiceTest (consumed, rollover, status, scope, D-01)</name>
  <files>backend/src/test/java/com/prosperity/envelope/EnvelopeServiceTest.java</files>
  <read_first>
    - backend/src/test/java/com/prosperity/envelope/EnvelopeServiceTest.java (current state — stubs from Plan 03)
    - backend/src/main/java/com/prosperity/envelope/EnvelopeService.java (Plan 04 output — exact methods to call)
    - backend/src/test/java/com/prosperity/transaction/TransactionControllerTest.java (canonical @BeforeEach + Autowired pattern)
    - backend/src/main/java/com/prosperity/category/Category.java (parent/child structure for D-02 test)
    - backend/src/main/resources/db/migration/V011__seed_plaid_categories.sql (deterministic seeded UUIDs you can use as fixtures)
  </read_first>
  <behavior>
For EVERY @Disabled test, remove @Disabled and write an AAA body that verifies the named scenario. Examples:

`budget_for_month_without_override_returns_envelope_default_budget`:
- Arrange: persist envelope with budget=100; no allocation row
- Act: `EnvelopeResponse r = envelopeService.getEnvelope(env.getId(), USER_EMAIL);`
- Assert: `assertThat(r.effectiveBudget()).isEqualByComparingTo(new BigDecimal("100.00")); assertThat(r.hasMonthlyOverride()).isFalse();`

`budget_for_month_with_override_returns_override_amount`:
- Arrange: persist envelope budget=100; persist allocation for current YearMonth at 250
- Act: `EnvelopeResponse r = envelopeService.getEnvelope(env.getId(), USER_EMAIL);`
- Assert: `assertThat(r.effectiveBudget()).isEqualByComparingTo(new BigDecimal("250.00")); assertThat(r.hasMonthlyOverride()).isTrue();`

`status_at_exactly_80_percent_is_yellow`:
- Arrange: budget 100, persist 1 transaction amount=-80 in current month linked-category
- Act: `EnvelopeResponse r = envelopeService.getEnvelope(env.getId(), USER_EMAIL);`
- Assert: `assertThat(r.status()).isEqualTo(EnvelopeStatus.YELLOW); assertThat(r.ratio()).isEqualByComparingTo(new BigDecimal("0.8000"));`

`transaction_on_first_day_of_next_month_excluded_from_previous_month_consumed` (Pitfall 7):
- Arrange: envelope on April; transaction with date=2026-05-01 in linked category
- Act: `EnvelopeResponse r = envelopeService.getEnvelopeHistory(env.getId(), YearMonth.of(2026, 4), USER_EMAIL).get(11);` // last entry = April
- Assert: `assertThat(r.consumed()).isEqualByComparingTo(BigDecimal.ZERO);`
  </behavior>
  <action>
Replace the contents of `backend/src/test/java/com/prosperity/envelope/EnvelopeServiceTest.java` with a fully implemented version following these rules:

**Class-level setup (mirrors TransactionControllerTest):**

```java
@SpringBootTest
@ActiveProfiles("test")
@Import(TestcontainersConfig.class)
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_EACH_TEST_METHOD)
class EnvelopeServiceTest {

  private static final String USER_EMAIL = "test@test.com";

  @Autowired private EnvelopeService envelopeService;
  @Autowired private EnvelopeRepository envelopeRepository;
  @Autowired private EnvelopeAllocationRepository allocationRepository;
  @Autowired private UserRepository userRepository;
  @Autowired private AccountRepository accountRepository;
  @Autowired private AccountAccessRepository accountAccessRepository;
  @Autowired private CategoryRepository categoryRepository;
  @Autowired private TransactionRepository transactionRepository;
  @Autowired private TransactionSplitRepository transactionSplitRepository;

  private User testUser;
  private Account testAccount;
  private Category testCategory; // a0000000-0000-0000-0000-000000000101 (Courses)
  private Category parentCategory; // for D-02 test

  @BeforeEach
  void setUp() {
    testUser = userRepository.save(new User(USER_EMAIL, "{bcrypt}$2a$10$hash", "Test User"));
    testAccount = accountRepository.save(new Account("Compte", AccountType.PERSONAL));
    accountAccessRepository.save(new AccountAccess(testUser, testAccount, AccessLevel.WRITE));
    testCategory =
        categoryRepository
            .findById(UUID.fromString("a0000000-0000-0000-0000-000000000101"))
            .orElseThrow();
    parentCategory = testCategory.getParent(); // root food category for D-02 child-of-root tests
  }

  // Helper builders (DAMP within a test, DRY for setup mechanism — testing-principles.md)
  private Envelope persistEnvelope(String name, BigDecimal budget, RolloverPolicy policy, Category... cats) {
    Envelope env = new Envelope(testAccount, name, EnvelopeScope.PERSONAL, new Money(budget));
    env.setOwner(testUser);
    env.setRolloverPolicy(policy);
    for (Category c : cats) env.getCategories().add(c);
    return envelopeRepository.save(env);
  }

  private Transaction persistTransaction(BigDecimal amount, LocalDate date, Category category) {
    Transaction t = new Transaction(testAccount, new Money(amount), date, TransactionSource.MANUAL);
    t.setCategory(category);
    return transactionRepository.save(t);
  }
  // ... fill in the rest
}
```

**Test rules (testing-principles.md compliance):**

1. **AAA structure with blank-line separation**:
   ```java
   @Test
   void status_at_exactly_80_percent_is_yellow() {
     // Arrange
     Envelope env = persistEnvelope("Vie quotidienne", new BigDecimal("100.00"), RolloverPolicy.RESET, testCategory);
     persistTransaction(new BigDecimal("-80.00"), LocalDate.now().withDayOfMonth(15), testCategory);

     // Act
     EnvelopeResponse response = envelopeService.getEnvelope(env.getId(), USER_EMAIL);

     // Assert
     assertThat(response.status()).isEqualTo(EnvelopeStatus.YELLOW);
     assertThat(response.ratio()).isEqualByComparingTo(new BigDecimal("0.8000"));
   }
   ```

2. **Act on ONE line.** If you need multi-step setup, put it in Arrange.

3. **Snake_case names already in place** (don't rename).

4. **No mocks.** Real Testcontainers PostgreSQL is the SUT collaborator.

5. **Money assertions use `isEqualByComparingTo`** (not `isEqualTo`) because BigDecimal scale matters (`100` != `100.00` for equals but compareTo is 0).

6. **Boundary cases (Pitfall 7):**
   - `transaction_on_last_day_of_month_included_in_that_month_consumed`: date = `LocalDate.of(2026, 4, 30)`, query March is YearMonth(2026,4)
   - `transaction_on_first_day_of_next_month_excluded_from_previous_month_consumed`: date = `LocalDate.of(2026, 5, 1)`, query is YearMonth(2026,4)

7. **`consumed_includes_child_category_transactions_when_root_is_linked` (D-02):**
   - persistEnvelope linked to `parentCategory` only
   - persist transaction with category = `testCategory` (child of parent)
   - assert consumed includes the transaction amount

8. **`consumed_includes_transaction_splits_matching_linked_categories` (D-03):**
   - persist a Transaction with NO category (or category = null) and amount=-200
   - persist a TransactionSplit linked to that transaction with category=testCategory and amount=-50 (and another split for another category amount=-150)
   - persistEnvelope linked to testCategory
   - assert consumed = 50

9. **`rollover_carry_over_with_negative_previous_remainder_clamps_to_zero`:**
   - Arrange envelope CARRY_OVER, budget 100
   - persist transaction last month amount=-150 (overspent)
   - persist transaction this month amount=-30
   - Act: getEnvelope(...)
   - Assert: `available = budget(100) + max(0, 100-150)(=0 clamp) - 30 = 70`

10. **`rollover_carry_over_lookback_limited_to_one_previous_month`:**
    - Arrange envelope CARRY_OVER, budget 100
    - persist transactions in month-2 amount=-200 (irrelevant), month-1 amount=-50, month=0 amount=-20
    - Act: getEnvelope(...)
    - Assert: `available = 100 + (100-50) - 20 = 130` (month-2 ignored)

11. **`create_envelope_on_personal_account_derives_scope_personal_and_sets_owner`:**
    - Arrange: prepare CreateEnvelopeRequest with name="X", categoryIds={testCategory.id}, budget=100, rolloverPolicy=RESET
    - Act: `EnvelopeResponse r = envelopeService.createEnvelope(testAccount.getId(), req, USER_EMAIL);`
    - Assert: `assertThat(r.scope()).isEqualTo(EnvelopeScope.PERSONAL); assertThat(r.ownerId()).isEqualTo(testUser.getId());`

12. **`create_envelope_on_shared_account_derives_scope_shared_and_owner_null`:**
    - Arrange: create a SHARED account with WRITE access for user
    - Act: createEnvelope on that shared account
    - Assert: `r.scope() == SHARED`, `r.ownerId() == null`

13. **`create_envelope_with_category_already_linked_on_account_throws_duplicate_exception`:**
    - Arrange: persist envelope A linked to testCategory
    - Act/Assert: `assertThatThrownBy(() -> envelopeService.createEnvelope(testAccount.getId(), req, USER_EMAIL)).isInstanceOf(DuplicateEnvelopeCategoryException.class);` (req categoryIds includes testCategory)

14. **`update_envelope_can_keep_its_existing_categories_without_triggering_duplicate_check`:**
    - Arrange: persist envelope linked to testCategory
    - Act: `envelopeService.updateEnvelope(env.getId(), new UpdateEnvelopeRequest("New name", Set.of(testCategory.getId()), null, null), USER_EMAIL);`
    - Assert: no exception thrown; updated name persisted

15. **`same_category_on_two_envelopes_on_different_accounts_is_allowed`:**
    - Arrange: persist envelope on testAccount linked to testCategory; create another account+access; persist envelope on second account also linked to testCategory
    - Assert: no exception thrown

16. **`status_when_budget_zero_returns_green_defensively`:**
    - Arrange: persistEnvelope with budget=0
    - Act: getEnvelope(...)
    - Assert: `assertThat(r.status()).isEqualTo(EnvelopeStatus.GREEN);`

For each of the 22 stub methods, write a body following these rules. Use `Math.min(50, body)` lines per test (testing-principles.md "The Giant" anti-pattern). If a body grows beyond 50 lines, split into separate tests.

Use these imports as a starting set:
```java
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
```
  </action>
  <verify>
    <automated>cd /home/negus/dev/prosperity && ./mvnw -pl backend test -Dtest=EnvelopeServiceTest -q 2>&1 | tail -30</automated>
  </verify>
  <acceptance_criteria>
    - `grep -c "@Disabled" backend/src/test/java/com/prosperity/envelope/EnvelopeServiceTest.java` returns 0
    - `grep -c "@Test" backend/src/test/java/com/prosperity/envelope/EnvelopeServiceTest.java` returns at least 22
    - `grep -c "// Arrange" backend/src/test/java/com/prosperity/envelope/EnvelopeServiceTest.java` returns at least 22
    - `grep -c "// Act" backend/src/test/java/com/prosperity/envelope/EnvelopeServiceTest.java` returns at least 22
    - `grep -c "// Assert" backend/src/test/java/com/prosperity/envelope/EnvelopeServiceTest.java` returns at least 22
    - `grep -c "isEqualByComparingTo" backend/src/test/java/com/prosperity/envelope/EnvelopeServiceTest.java` returns at least 5 (BigDecimal assertions)
    - `grep -c "DuplicateEnvelopeCategoryException" backend/src/test/java/com/prosperity/envelope/EnvelopeServiceTest.java` returns at least 1
    - `grep -c "RolloverPolicy.CARRY_OVER" backend/src/test/java/com/prosperity/envelope/EnvelopeServiceTest.java` returns at least 3 (rollover suite)
    - `grep -c "EnvelopeStatus.YELLOW" backend/src/test/java/com/prosperity/envelope/EnvelopeServiceTest.java` returns at least 2 (80% + 100% boundaries)
    - `grep -c "Mockito" backend/src/test/java/com/prosperity/envelope/EnvelopeServiceTest.java` returns 0 (no mocking the data layer)
    - `./mvnw -pl backend test -Dtest=EnvelopeServiceTest` exits 0; surefire summary shows 22+ tests passed and 0 skipped
  </acceptance_criteria>
  <done>EnvelopeServiceTest passes — 22+ tests green; no @Disabled remain; AAA structure used throughout; no Mockito.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Fill EnvelopeControllerTest + EnvelopeAllocationControllerTest (MockMvc)</name>
  <files>backend/src/test/java/com/prosperity/envelope/EnvelopeControllerTest.java, backend/src/test/java/com/prosperity/envelope/EnvelopeAllocationControllerTest.java</files>
  <read_first>
    - backend/src/test/java/com/prosperity/envelope/EnvelopeControllerTest.java (current stubs)
    - backend/src/test/java/com/prosperity/envelope/EnvelopeAllocationControllerTest.java (current stubs)
    - backend/src/test/java/com/prosperity/transaction/TransactionControllerTest.java (canonical MockMvc + .with(user("...")) + .with(csrf()) pattern)
    - backend/src/main/java/com/prosperity/envelope/EnvelopeController.java (route paths)
    - backend/src/main/java/com/prosperity/envelope/EnvelopeAllocationController.java (route paths)
  </read_first>
  <behavior>
For each MockMvc-based test, perform the HTTP request via MockMvc with:
- `.with(user("test@test.com"))` for auth
- `.with(csrf())` on POST/PUT/DELETE
- `.contentType(MediaType.APPLICATION_JSON)` and `.content("...")` body where applicable
- assert `status()` (201 / 200 / 204 / 403 / 404 / 409)
- assert `jsonPath()` on response fields

Examples:

`create_envelope_on_personal_account_sets_scope_personal_and_owner_current_user`:
```java
mockMvc.perform(
    post("/api/accounts/{accountId}/envelopes", testAccount.getId())
        .with(user(USER_EMAIL)).with(csrf())
        .contentType(MediaType.APPLICATION_JSON)
        .content(String.format("""
            {"name":"Vie quotidienne","categoryIds":["%s"],"budget":100.00,"rolloverPolicy":"RESET"}
            """, testCategory.getId())))
    .andExpect(status().isCreated())
    .andExpect(jsonPath("$.scope").value("PERSONAL"))
    .andExpect(jsonPath("$.ownerId").value(testUser.getId().toString()));
```

`create_envelope_without_write_access_returns_403`:
- Arrange: create another user with READ-only access
- Act: POST as that user
- Assert: status 403

`create_envelope_with_category_already_linked_on_account_returns_409`:
- Arrange: persist envelope A linked to testCategory
- Act: POST creating envelope B linked to testCategory
- Assert: status 409

`get_envelope_history_returns_12_months_ordered_chronologically`:
- Act: `mockMvc.perform(get("/api/envelopes/{id}/history?month=2026-04", env.getId()).with(user(USER_EMAIL)))`
- Assert: `jsonPath("$.length()").value(12)` ; `jsonPath("$[0].month").value("2025-05")` ; `jsonPath("$[11].month").value("2026-04")`

`delete_envelope_with_allocations_soft_deletes_and_excludes_from_list`:
- Arrange: persist envelope + persist allocation
- Act: DELETE then GET
- Assert: status 204 on DELETE; GET list does NOT include the envelope (default excludes archived)
- Verify in DB: `envelopeRepository.findById(env.getId()).orElseThrow().isArchived()` is true
  </behavior>
  <action>
Replace the contents of both test files with fully implemented versions:

**For `EnvelopeControllerTest.java`:**

- Use the same `@BeforeEach` setup as EnvelopeServiceTest (testUser, testAccount, accountAccess, testCategory).
- Add `@Autowired private MockMvc mockMvc;` and `@Autowired private ObjectMapper objectMapper;` if needed.
- For each disabled stub, write a MockMvc-based AAA body following the examples above.
- Use `.with(user(USER_EMAIL))` for auth (matches Spring Security test convention from TransactionControllerTest).
- Use `.with(csrf())` on POST/PUT/DELETE.
- Use `String.format` for JSON bodies that need to embed UUIDs (matches TransactionControllerTest style).
- Use `jsonPath` assertions on response — assert ONLY the relevant fields, never the whole object (testing-principles.md "The Nitpicker").
- For tests that need a second user (access denied scenarios), create them inline in Arrange.
- For tests that need a SHARED account, create it inline.
- Use `LocalDate.of(2026, 4, 15)` (or current month equivalent via `LocalDate.now()`) — but BE EXPLICIT with dates for boundary tests (Pitfall 7) so they aren't time-dependent in CI.
- For history tests, parameterize the request with `?month=2026-04` and assert exact months in the response.
- For delete-with-allocations test, after the DELETE call, assert via repository that `envelopeRepository.findById(env.getId())` returns a present, archived envelope.

**For `EnvelopeAllocationControllerTest.java`:**

- Same `@BeforeEach`.
- For each stub, write a body. Examples:

`create_allocation_for_envelope_returns_201_with_response`:
```java
Envelope env = envelopeRepository.save(...);  // arrange
mockMvc.perform(post("/api/envelopes/{id}/allocations", env.getId())
        .with(user(USER_EMAIL)).with(csrf())
        .contentType(MediaType.APPLICATION_JSON)
        .content("""{"month":"2026-04","allocatedAmount":250.00}"""))
    .andExpect(status().isCreated())
    .andExpect(jsonPath("$.month").value("2026-04"))
    .andExpect(jsonPath("$.allocatedAmount").value(250.00));
```

`duplicate_allocation_for_same_month_returns_409`:
- Arrange: persist allocation for env+April
- Act: POST another for env+April
- Assert: 409

`list_allocations_for_envelope_returns_overrides_ordered_by_month_asc`:
- Arrange: persist 3 allocations (June, January, March)
- Act: GET
- Assert: `$[0].month == 2026-01`, `$[1].month == 2026-03`, `$[2].month == 2026-06`

`update_allocation_replaces_allocated_amount_for_month`:
- Arrange: persist allocation
- Act: PUT /api/envelopes/allocations/{allocationId} with new amount
- Assert: 200 + jsonPath amount changed

`delete_allocation_removes_override_and_falls_back_to_default_budget`:
- Arrange: persist envelope budget=100 + allocation 250
- Act: DELETE allocation
- Assert: 204 + GET envelope shows effectiveBudget=100, hasMonthlyOverride=false

Apply the same style + AAA discipline.

**Common imports for both files:**
```java
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;
```
  </action>
  <verify>
    <automated>cd /home/negus/dev/prosperity && ./mvnw -pl backend test -Dtest='Envelope*Test' -q 2>&1 | tail -30</automated>
  </verify>
  <acceptance_criteria>
    - `grep -c "@Disabled" backend/src/test/java/com/prosperity/envelope/EnvelopeControllerTest.java` returns 0
    - `grep -c "@Disabled" backend/src/test/java/com/prosperity/envelope/EnvelopeAllocationControllerTest.java` returns 0
    - `grep -c "mockMvc.perform" backend/src/test/java/com/prosperity/envelope/EnvelopeControllerTest.java` returns at least 21
    - `grep -c "mockMvc.perform" backend/src/test/java/com/prosperity/envelope/EnvelopeAllocationControllerTest.java` returns at least 7
    - `grep -c "status().isCreated()" backend/src/test/java/com/prosperity/envelope/EnvelopeControllerTest.java` returns at least 1
    - `grep -c "status().isForbidden()" backend/src/test/java/com/prosperity/envelope/EnvelopeControllerTest.java` returns at least 3 (3 access-denied scenarios)
    - `grep -c "status().isNotFound()" backend/src/test/java/com/prosperity/envelope/EnvelopeControllerTest.java` returns at least 2
    - `grep -c "status().isConflict()" backend/src/test/java/com/prosperity/envelope/EnvelopeControllerTest.java` returns at least 1
    - `grep -c "status().isNoContent()" backend/src/test/java/com/prosperity/envelope/EnvelopeControllerTest.java` returns at least 1 (DELETE)
    - `grep -c "status().isConflict()" backend/src/test/java/com/prosperity/envelope/EnvelopeAllocationControllerTest.java` returns at least 1
    - `./mvnw -pl backend test -Dtest='Envelope*Test'` exits 0; surefire summary shows total tests >= 50, 0 skipped, 0 failures, 0 errors
    - `./mvnw -pl backend verify -q` exits 0 (full verification including JaCoCo + Checkstyle gates)
  </acceptance_criteria>
  <done>Both controller test files passing — 28+ tests across both — and the full backend verify (./mvnw verify) is green.</done>
</task>

</tasks>

<verification>
- `./mvnw -pl backend test -Dtest='Envelope*Test'` exits 0 with all 50+ tests green and 0 skipped.
- `./mvnw verify` exits 0 — Checkstyle clean, JaCoCo thresholds maintained (70% instruction, 50% branch), OWASP scan clean.
- 06-VALIDATION.md `wave_0_complete: true` becomes plausible (Plan 08 will finalise once frontend tests land).
</verification>

<success_criteria>
- Zero @Disabled annotations remain in any envelope test file.
- Each test follows AAA with Act on one line.
- Test names already describe scenarios; bodies prove them.
- 50+ tests passing across the 3 files.
- ./mvnw verify exits 0.
</success_criteria>

<output>
After completion, create `.planning/phases/06-envelope-budgets/06-06-backend-tests-SUMMARY.md`.
</output>
