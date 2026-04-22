package com.prosperity.envelope;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.prosperity.TestcontainersConfig;
import com.prosperity.account.AccessLevel;
import com.prosperity.account.Account;
import com.prosperity.account.AccountAccess;
import com.prosperity.account.AccountAccessRepository;
import com.prosperity.account.AccountRepository;
import com.prosperity.auth.User;
import com.prosperity.auth.UserRepository;
import com.prosperity.category.Category;
import com.prosperity.category.CategoryRepository;
import com.prosperity.shared.AccountType;
import com.prosperity.shared.EnvelopeScope;
import com.prosperity.shared.Money;
import com.prosperity.shared.RolloverPolicy;
import com.prosperity.shared.TransactionSource;
import com.prosperity.transaction.Transaction;
import com.prosperity.transaction.TransactionRepository;
import com.prosperity.transaction.TransactionSplit;
import com.prosperity.transaction.TransactionSplitRepository;
import java.math.BigDecimal;
import java.time.LocalDate;
import java.time.YearMonth;
import java.time.ZoneId;
import java.util.List;
import java.util.Set;
import java.util.UUID;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.context.ActiveProfiles;

/**
 * Behavior tests for {@link EnvelopeService} backed by a real PostgreSQL via Testcontainers (no
 * mocking of the data layer per testing-principles.md).
 *
 * <p>Coverage map (mirrors 06-RESEARCH.md "Phase Requirements -> Test Map"):
 *
 * <ul>
 *   <li>ENVL-02: default vs override budget resolution
 *   <li>ENVL-03: consumed aggregation (transactions + splits + recursive CTE + boundaries + D-04)
 *   <li>ENVL-04: rollover formula (RESET, CARRY_OVER positive, CARRY_OVER negative -> 0, lookback)
 *   <li>ENVL-05: status thresholds (GREEN, YELLOW, RED + 80%/100% boundaries)
 *   <li>ENVL-01 service slice: scope derivation from account type, D-01 uniqueness
 * </ul>
 */
@SpringBootTest
@ActiveProfiles("test")
@Import(TestcontainersConfig.class)
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_EACH_TEST_METHOD)
class EnvelopeServiceTest {

  private static final String USER_EMAIL = "test@test.com";
  private static final UUID COURSES_CATEGORY_ID =
      UUID.fromString("a0000000-0000-0000-0000-000000000101");
  private static final UUID RESTAURANT_CATEGORY_ID =
      UUID.fromString("a0000000-0000-0000-0000-000000000102");
  private static final UUID CARBURANT_CATEGORY_ID =
      UUID.fromString("a0000000-0000-0000-0000-000000000201");

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
  private Category coursesCategory; // leaf "Courses" child of "Alimentation & Restauration"
  private Category alimentationCategory; // root "Alimentation & Restauration"
  private Category restaurantCategory; // leaf "Restaurant" child of alimentation root
  private Category carburantCategory; // leaf in a DIFFERENT root tree (Transport -> Carburant)

  @BeforeEach
  void setUp() {
    testUser = userRepository.save(new User(USER_EMAIL, "{bcrypt}$2a$10$hash", "Test User"));
    testAccount = accountRepository.save(new Account("Compte Courant", AccountType.PERSONAL));
    accountAccessRepository.save(new AccountAccess(testUser, testAccount, AccessLevel.WRITE));

    coursesCategory = categoryRepository.findById(COURSES_CATEGORY_ID).orElseThrow();
    alimentationCategory = coursesCategory.getParent();
    restaurantCategory = categoryRepository.findById(RESTAURANT_CATEGORY_ID).orElseThrow();
    carburantCategory = categoryRepository.findById(CARBURANT_CATEGORY_ID).orElseThrow();
  }

  // -------------------------------------------------------------------------
  // Test data builders (DRY mechanism, DAMP scenarios — testing-principles.md)
  // -------------------------------------------------------------------------

  private Envelope persistEnvelope(
      Account account, BigDecimal budget, RolloverPolicy policy, Category... cats) {
    EnvelopeScope scope =
        account.getAccountType() == AccountType.SHARED
            ? EnvelopeScope.SHARED
            : EnvelopeScope.PERSONAL;
    Envelope envelope = new Envelope(account, "Vie quotidienne", scope, new Money(budget));
    envelope.setOwner(scope == EnvelopeScope.PERSONAL ? testUser : null);
    envelope.setRolloverPolicy(policy);
    for (Category c : cats) {
      envelope.getCategories().add(c);
    }
    return envelopeRepository.save(envelope);
  }

  private Transaction persistTransaction(BigDecimal amount, LocalDate date, Category category) {
    Transaction tx =
        new Transaction(testAccount, new Money(amount), date, TransactionSource.MANUAL);
    tx.setCategory(category);
    tx.setCreatedBy(testUser);
    return transactionRepository.save(tx);
  }

  private Transaction persistSplitParentTransaction(BigDecimal amount, LocalDate date) {
    Transaction tx =
        new Transaction(testAccount, new Money(amount), date, TransactionSource.MANUAL);
    tx.setCreatedBy(testUser);
    return transactionRepository.save(tx);
  }

  private void persistAllocation(Envelope envelope, YearMonth month, BigDecimal amount) {
    allocationRepository.save(new EnvelopeAllocation(envelope, month, new Money(amount)));
  }

  private YearMonth fixedMonth() {
    // Deterministic month for all boundary-sensitive tests (Pitfall 7).
    return YearMonth.of(2026, 4);
  }

  private LocalDate midMonth() {
    return LocalDate.of(2026, 4, 15);
  }

  // -------------------------------------------------------------------------
  // ENVL-02 — Budget resolution (override vs default)
  // -------------------------------------------------------------------------

  @Test
  void budget_for_month_without_override_returns_envelope_default_budget() {
    // Arrange
    Envelope envelope =
        persistEnvelope(testAccount, new BigDecimal("100.00"), RolloverPolicy.RESET, coursesCategory);

    // Act
    EnvelopeResponse response = envelopeService.getEnvelope(envelope.getId(), USER_EMAIL);

    // Assert
    assertThat(response.effectiveBudget()).isEqualByComparingTo(new BigDecimal("100.00"));
    assertThat(response.hasMonthlyOverride()).isFalse();
  }

  @Test
  void budget_for_month_with_override_returns_override_amount() {
    // Arrange
    Envelope envelope =
        persistEnvelope(testAccount, new BigDecimal("100.00"), RolloverPolicy.RESET, coursesCategory);
    persistAllocation(envelope, currentMonth(), new BigDecimal("250.00"));

    // Act
    EnvelopeResponse response = envelopeService.getEnvelope(envelope.getId(), USER_EMAIL);

    // Assert
    assertThat(response.effectiveBudget()).isEqualByComparingTo(new BigDecimal("250.00"));
    assertThat(response.hasMonthlyOverride()).isTrue();
  }

  // -------------------------------------------------------------------------
  // ENVL-03 — Consumed aggregation
  // -------------------------------------------------------------------------

  @Test
  void consumed_sums_negative_transactions_in_linked_categories() {
    // Arrange
    Envelope envelope =
        persistEnvelope(testAccount, new BigDecimal("500.00"), RolloverPolicy.RESET, coursesCategory);
    LocalDate today = LocalDate.now(ZoneId.systemDefault()).withDayOfMonth(10);
    persistTransaction(new BigDecimal("-45.30"), today, coursesCategory);
    persistTransaction(new BigDecimal("-12.00"), today.plusDays(1), coursesCategory);

    // Act
    EnvelopeResponse response = envelopeService.getEnvelope(envelope.getId(), USER_EMAIL);

    // Assert
    assertThat(response.consumed()).isEqualByComparingTo(new BigDecimal("57.30"));
  }

  @Test
  void consumed_includes_transaction_splits_matching_linked_categories() {
    // Arrange — envelope linked to courses only; split parent has no category, two splits (one match, one miss)
    Envelope envelope =
        persistEnvelope(testAccount, new BigDecimal("500.00"), RolloverPolicy.RESET, coursesCategory);
    Transaction parent = persistSplitParentTransaction(new BigDecimal("-200.00"), midMonthCurrent());
    transactionSplitRepository.save(
        new TransactionSplit(parent, coursesCategory, new Money(new BigDecimal("-50.00"))));
    transactionSplitRepository.save(
        new TransactionSplit(parent, carburantCategory, new Money(new BigDecimal("-150.00"))));

    // Act
    EnvelopeResponse response = envelopeService.getEnvelope(envelope.getId(), USER_EMAIL);

    // Assert
    assertThat(response.consumed()).isEqualByComparingTo(new BigDecimal("50.00"));
  }

  @Test
  void consumed_includes_child_category_transactions_when_root_is_linked() {
    // Arrange — envelope linked to ROOT (alimentation); transaction under child (courses) — D-02 recursive CTE
    Envelope envelope =
        persistEnvelope(
            testAccount, new BigDecimal("500.00"), RolloverPolicy.RESET, alimentationCategory);
    persistTransaction(new BigDecimal("-80.00"), midMonthCurrent(), coursesCategory);

    // Act
    EnvelopeResponse response = envelopeService.getEnvelope(envelope.getId(), USER_EMAIL);

    // Assert
    assertThat(response.consumed()).isEqualByComparingTo(new BigDecimal("80.00"));
  }

  @Test
  void transaction_in_unlinked_category_does_not_affect_consumed() {
    // Arrange — envelope linked to courses only; transaction in carburant (different root tree)
    Envelope envelope =
        persistEnvelope(testAccount, new BigDecimal("500.00"), RolloverPolicy.RESET, coursesCategory);
    persistTransaction(new BigDecimal("-60.00"), midMonthCurrent(), carburantCategory);

    // Act
    EnvelopeResponse response = envelopeService.getEnvelope(envelope.getId(), USER_EMAIL);

    // Assert
    assertThat(response.consumed()).isEqualByComparingTo(BigDecimal.ZERO);
  }

  @Test
  void transaction_on_last_day_of_month_included_in_that_month_consumed() {
    // Arrange — Pitfall 7 boundary: last day of April must land in April bucket
    Envelope envelope =
        persistEnvelope(testAccount, new BigDecimal("500.00"), RolloverPolicy.RESET, coursesCategory);
    persistTransaction(new BigDecimal("-40.00"), LocalDate.of(2026, 4, 30), coursesCategory);

    // Act
    List<EnvelopeHistoryEntry> history =
        envelopeService.getEnvelopeHistory(envelope.getId(), fixedMonth(), USER_EMAIL);

    // Assert — last entry of the 12-month window is April 2026
    EnvelopeHistoryEntry april = history.get(11);
    assertThat(april.month()).isEqualTo(fixedMonth());
    assertThat(april.consumed()).isEqualByComparingTo(new BigDecimal("40.00"));
  }

  @Test
  void transaction_on_first_day_of_next_month_excluded_from_previous_month_consumed() {
    // Arrange — Pitfall 7: 2026-05-01 must NOT land in April bucket
    Envelope envelope =
        persistEnvelope(testAccount, new BigDecimal("500.00"), RolloverPolicy.RESET, coursesCategory);
    persistTransaction(new BigDecimal("-40.00"), LocalDate.of(2026, 5, 1), coursesCategory);

    // Act
    List<EnvelopeHistoryEntry> history =
        envelopeService.getEnvelopeHistory(envelope.getId(), fixedMonth(), USER_EMAIL);

    // Assert — April bucket is zero (transaction belongs to May, outside the 12-month window)
    EnvelopeHistoryEntry april = history.get(11);
    assertThat(april.month()).isEqualTo(fixedMonth());
    assertThat(april.consumed()).isEqualByComparingTo(BigDecimal.ZERO);
  }

  @Test
  void consumed_for_envelope_without_categories_returns_zero() {
    // Arrange — envelope with zero linked categories (no cats in the constructor call)
    Envelope envelope =
        persistEnvelope(testAccount, new BigDecimal("500.00"), RolloverPolicy.RESET);
    persistTransaction(new BigDecimal("-100.00"), midMonthCurrent(), coursesCategory);

    // Act
    EnvelopeResponse response = envelopeService.getEnvelope(envelope.getId(), USER_EMAIL);

    // Assert
    assertThat(response.consumed()).isEqualByComparingTo(BigDecimal.ZERO);
  }

  @Test
  void split_parent_with_non_null_category_is_counted_only_via_splits_branch() {
    // Arrange — D-03 defensive NOT EXISTS dedup: parent has category=courses AND splits exist
    Envelope envelope =
        persistEnvelope(testAccount, new BigDecimal("500.00"), RolloverPolicy.RESET, coursesCategory);
    Transaction parent =
        persistTransaction(new BigDecimal("-100.00"), midMonthCurrent(), coursesCategory);
    transactionSplitRepository.save(
        new TransactionSplit(parent, coursesCategory, new Money(new BigDecimal("-60.00"))));
    transactionSplitRepository.save(
        new TransactionSplit(parent, carburantCategory, new Money(new BigDecimal("-40.00"))));

    // Act
    EnvelopeResponse response = envelopeService.getEnvelope(envelope.getId(), USER_EMAIL);

    // Assert — parent excluded (NOT EXISTS dedup); only splits matching courses counted = 60
    assertThat(response.consumed()).isEqualByComparingTo(new BigDecimal("60.00"));
  }

  // -------------------------------------------------------------------------
  // ENVL-04 — Rollover (RESET, CARRY_OVER, lookback)
  // -------------------------------------------------------------------------

  @Test
  void rollover_reset_policy_ignores_previous_month() {
    // Arrange — RESET envelope; previous month had remainder, current month has no consumption
    Envelope envelope =
        persistEnvelope(testAccount, new BigDecimal("100.00"), RolloverPolicy.RESET, coursesCategory);
    persistTransaction(
        new BigDecimal("-30.00"), LocalDate.now(ZoneId.systemDefault()).minusMonths(1).withDayOfMonth(15), coursesCategory);

    // Act
    EnvelopeResponse response = envelopeService.getEnvelope(envelope.getId(), USER_EMAIL);

    // Assert — available = budget (no carry-over), ratio = 0
    assertThat(response.available()).isEqualByComparingTo(new BigDecimal("100.00"));
    assertThat(response.ratio()).isEqualByComparingTo(BigDecimal.ZERO);
  }

  @Test
  void rollover_carry_over_with_positive_previous_remainder_adds_to_available() {
    // Arrange — CARRY_OVER: prev remainder = 100 - 30 = 70; current consumed = 20
    Envelope envelope =
        persistEnvelope(
            testAccount, new BigDecimal("100.00"), RolloverPolicy.CARRY_OVER, coursesCategory);
    persistTransaction(
        new BigDecimal("-30.00"), LocalDate.now(ZoneId.systemDefault()).minusMonths(1).withDayOfMonth(15), coursesCategory);
    persistTransaction(new BigDecimal("-20.00"), LocalDate.now(ZoneId.systemDefault()).withDayOfMonth(10), coursesCategory);

    // Act
    EnvelopeResponse response = envelopeService.getEnvelope(envelope.getId(), USER_EMAIL);

    // Assert — allocatable = 100 + 70 = 170; available = 170 - 20 = 150
    assertThat(response.available()).isEqualByComparingTo(new BigDecimal("150.00"));
  }

  @Test
  void rollover_carry_over_with_negative_previous_remainder_clamps_to_zero() {
    // Arrange — CARRY_OVER: prev overspent (-150 on budget 100 -> raw remainder = -50, clamped to 0)
    Envelope envelope =
        persistEnvelope(
            testAccount, new BigDecimal("100.00"), RolloverPolicy.CARRY_OVER, coursesCategory);
    persistTransaction(
        new BigDecimal("-150.00"),
        LocalDate.now(ZoneId.systemDefault()).minusMonths(1).withDayOfMonth(15),
        coursesCategory);
    persistTransaction(new BigDecimal("-30.00"), LocalDate.now(ZoneId.systemDefault()).withDayOfMonth(10), coursesCategory);

    // Act
    EnvelopeResponse response = envelopeService.getEnvelope(envelope.getId(), USER_EMAIL);

    // Assert — allocatable = 100 + max(0, -50) = 100; available = 100 - 30 = 70
    assertThat(response.available()).isEqualByComparingTo(new BigDecimal("70.00"));
  }

  @Test
  void rollover_carry_over_lookback_limited_to_one_previous_month() {
    // Arrange — month-2 must be IGNORED; only month-1 feeds carryOver
    Envelope envelope =
        persistEnvelope(
            testAccount, new BigDecimal("100.00"), RolloverPolicy.CARRY_OVER, coursesCategory);
    persistTransaction(
        new BigDecimal("-200.00"),
        LocalDate.now(ZoneId.systemDefault()).minusMonths(2).withDayOfMonth(15),
        coursesCategory);
    persistTransaction(
        new BigDecimal("-50.00"), LocalDate.now(ZoneId.systemDefault()).minusMonths(1).withDayOfMonth(15), coursesCategory);
    persistTransaction(new BigDecimal("-20.00"), LocalDate.now(ZoneId.systemDefault()).withDayOfMonth(10), coursesCategory);

    // Act
    EnvelopeResponse response = envelopeService.getEnvelope(envelope.getId(), USER_EMAIL);

    // Assert — carry = max(0, 100 - 50) = 50; allocatable = 150; available = 150 - 20 = 130
    assertThat(response.available()).isEqualByComparingTo(new BigDecimal("130.00"));
  }

  // -------------------------------------------------------------------------
  // ENVL-05 — Status thresholds (D-13 boundaries)
  // -------------------------------------------------------------------------

  @Test
  void status_when_consumed_is_zero_returns_green() {
    // Arrange
    Envelope envelope =
        persistEnvelope(testAccount, new BigDecimal("100.00"), RolloverPolicy.RESET, coursesCategory);

    // Act
    EnvelopeResponse response = envelopeService.getEnvelope(envelope.getId(), USER_EMAIL);

    // Assert
    assertThat(response.status()).isEqualTo(EnvelopeStatus.GREEN);
    assertThat(response.ratio()).isEqualByComparingTo(BigDecimal.ZERO);
  }

  @Test
  void status_when_consumed_below_eighty_percent_returns_green() {
    // Arrange — 79% ratio (just below YELLOW boundary)
    Envelope envelope =
        persistEnvelope(testAccount, new BigDecimal("100.00"), RolloverPolicy.RESET, coursesCategory);
    persistTransaction(new BigDecimal("-79.00"), LocalDate.now(ZoneId.systemDefault()).withDayOfMonth(10), coursesCategory);

    // Act
    EnvelopeResponse response = envelopeService.getEnvelope(envelope.getId(), USER_EMAIL);

    // Assert
    assertThat(response.status()).isEqualTo(EnvelopeStatus.GREEN);
  }

  @Test
  void status_at_exactly_80_percent_is_yellow() {
    // Arrange — BVA: ratio = 0.80 (inclusive lower bound of YELLOW)
    Envelope envelope =
        persistEnvelope(testAccount, new BigDecimal("100.00"), RolloverPolicy.RESET, coursesCategory);
    persistTransaction(new BigDecimal("-80.00"), LocalDate.now(ZoneId.systemDefault()).withDayOfMonth(10), coursesCategory);

    // Act
    EnvelopeResponse response = envelopeService.getEnvelope(envelope.getId(), USER_EMAIL);

    // Assert
    assertThat(response.status()).isEqualTo(EnvelopeStatus.YELLOW);
    assertThat(response.ratio()).isEqualByComparingTo(new BigDecimal("0.8000"));
  }

  @Test
  void status_at_exactly_100_percent_is_yellow_and_above_is_red() {
    // Arrange — BVA: ratio = 1.00 (inclusive upper bound of YELLOW)
    Envelope envelope =
        persistEnvelope(testAccount, new BigDecimal("100.00"), RolloverPolicy.RESET, coursesCategory);
    persistTransaction(
        new BigDecimal("-100.00"), LocalDate.now(ZoneId.systemDefault()).withDayOfMonth(10), coursesCategory);

    // Act
    EnvelopeResponse response = envelopeService.getEnvelope(envelope.getId(), USER_EMAIL);

    // Assert
    assertThat(response.status()).isEqualTo(EnvelopeStatus.YELLOW);
    assertThat(response.ratio()).isEqualByComparingTo(new BigDecimal("1.0000"));
  }

  @Test
  void status_above_100_percent_returns_red() {
    // Arrange — ratio > 1.00 strictly
    Envelope envelope =
        persistEnvelope(testAccount, new BigDecimal("100.00"), RolloverPolicy.RESET, coursesCategory);
    persistTransaction(
        new BigDecimal("-120.00"), LocalDate.now(ZoneId.systemDefault()).withDayOfMonth(10), coursesCategory);

    // Act
    EnvelopeResponse response = envelopeService.getEnvelope(envelope.getId(), USER_EMAIL);

    // Assert
    assertThat(response.status()).isEqualTo(EnvelopeStatus.RED);
    assertThat(response.ratio().compareTo(new BigDecimal("1.00"))).isGreaterThan(0);
  }

  @Test
  void status_when_budget_zero_returns_green_defensively() {
    // Arrange — defensive: allocatable = 0 -> ratio = 0 -> GREEN (D-13 defensive branch)
    Envelope envelope =
        persistEnvelope(testAccount, BigDecimal.ZERO, RolloverPolicy.RESET, coursesCategory);

    // Act
    EnvelopeResponse response = envelopeService.getEnvelope(envelope.getId(), USER_EMAIL);

    // Assert
    assertThat(response.status()).isEqualTo(EnvelopeStatus.GREEN);
    assertThat(response.ratio()).isEqualByComparingTo(BigDecimal.ZERO);
  }

  @Test
  void ratio_denominator_includes_carry_over_for_carry_over_envelopes() {
    // Arrange — D-13 literal: denominator = effectiveBudget + carryOver (not just budget)
    // budget=100, prev consumed 40 -> carry=60; current consumed=90; allocatable=160; ratio=90/160=0.5625
    Envelope envelope =
        persistEnvelope(
            testAccount, new BigDecimal("100.00"), RolloverPolicy.CARRY_OVER, coursesCategory);
    persistTransaction(
        new BigDecimal("-40.00"), LocalDate.now(ZoneId.systemDefault()).minusMonths(1).withDayOfMonth(15), coursesCategory);
    persistTransaction(new BigDecimal("-90.00"), LocalDate.now(ZoneId.systemDefault()).withDayOfMonth(10), coursesCategory);

    // Act
    EnvelopeResponse response = envelopeService.getEnvelope(envelope.getId(), USER_EMAIL);

    // Assert — ratio denominator = 160, not 100 (would be 0.9 if computed over budget alone)
    assertThat(response.ratio()).isEqualByComparingTo(new BigDecimal("0.5625"));
    assertThat(response.status()).isEqualTo(EnvelopeStatus.GREEN);
  }

  // -------------------------------------------------------------------------
  // ENVL-01 service slice — scope derivation + D-01 uniqueness
  // -------------------------------------------------------------------------

  @Test
  void create_envelope_on_personal_account_derives_scope_personal_and_sets_owner() {
    // Arrange
    CreateEnvelopeRequest request =
        new CreateEnvelopeRequest(
            "Vie quotidienne",
            Set.of(coursesCategory.getId()),
            new BigDecimal("100.00"),
            RolloverPolicy.RESET);

    // Act
    EnvelopeResponse response =
        envelopeService.createEnvelope(testAccount.getId(), request, USER_EMAIL);

    // Assert
    assertThat(response.scope()).isEqualTo(EnvelopeScope.PERSONAL);
    assertThat(response.ownerId()).isEqualTo(testUser.getId());
  }

  @Test
  void create_envelope_on_shared_account_derives_scope_shared_and_owner_null() {
    // Arrange — second account, SHARED, same user has WRITE access
    Account sharedAccount =
        accountRepository.save(new Account("Compte Foyer", AccountType.SHARED));
    accountAccessRepository.save(new AccountAccess(testUser, sharedAccount, AccessLevel.WRITE));
    CreateEnvelopeRequest request =
        new CreateEnvelopeRequest(
            "Courses foyer",
            Set.of(coursesCategory.getId()),
            new BigDecimal("400.00"),
            RolloverPolicy.RESET);

    // Act
    EnvelopeResponse response =
        envelopeService.createEnvelope(sharedAccount.getId(), request, USER_EMAIL);

    // Assert
    assertThat(response.scope()).isEqualTo(EnvelopeScope.SHARED);
    assertThat(response.ownerId()).isNull();
  }

  @Test
  void create_envelope_with_category_already_linked_on_account_throws_duplicate_exception() {
    // Arrange — envelope A already links courses on testAccount
    persistEnvelope(testAccount, new BigDecimal("100.00"), RolloverPolicy.RESET, coursesCategory);
    CreateEnvelopeRequest request =
        new CreateEnvelopeRequest(
            "Autre",
            Set.of(coursesCategory.getId()),
            new BigDecimal("50.00"),
            RolloverPolicy.RESET);

    // Act + Assert
    assertThatThrownBy(
            () -> envelopeService.createEnvelope(testAccount.getId(), request, USER_EMAIL))
        .isInstanceOf(DuplicateEnvelopeCategoryException.class);
  }

  @Test
  void update_envelope_can_keep_its_existing_categories_without_triggering_duplicate_check() {
    // Arrange — envelope linked to courses; PATCH keeps same category and changes name
    Envelope envelope =
        persistEnvelope(testAccount, new BigDecimal("100.00"), RolloverPolicy.RESET, coursesCategory);
    UpdateEnvelopeRequest request =
        new UpdateEnvelopeRequest("Renamed", Set.of(coursesCategory.getId()), null, null);

    // Act
    EnvelopeResponse response =
        envelopeService.updateEnvelope(envelope.getId(), request, USER_EMAIL);

    // Assert — no exception thrown; name updated; category preserved
    assertThat(response.name()).isEqualTo("Renamed");
    assertThat(response.categories()).hasSize(1);
    assertThat(response.categories().get(0).id()).isEqualTo(coursesCategory.getId());
  }

  @Test
  void same_category_on_two_envelopes_on_different_accounts_is_allowed() {
    // Arrange — second account, same user has WRITE access, courses linked on first
    persistEnvelope(testAccount, new BigDecimal("100.00"), RolloverPolicy.RESET, coursesCategory);
    Account secondAccount =
        accountRepository.save(new Account("Compte Epargne", AccountType.PERSONAL));
    accountAccessRepository.save(new AccountAccess(testUser, secondAccount, AccessLevel.WRITE));
    CreateEnvelopeRequest request =
        new CreateEnvelopeRequest(
            "Courses epargne",
            Set.of(coursesCategory.getId()),
            new BigDecimal("50.00"),
            RolloverPolicy.RESET);

    // Act
    EnvelopeResponse response =
        envelopeService.createEnvelope(secondAccount.getId(), request, USER_EMAIL);

    // Assert — D-01 scoped per account: second envelope on different account allowed
    assertThat(response.bankAccountId()).isEqualTo(secondAccount.getId());
  }

  // -------------------------------------------------------------------------
  // Helpers
  // -------------------------------------------------------------------------

  private LocalDate midMonthCurrent() {
    return LocalDate.now(ZoneId.systemDefault()).withDayOfMonth(10);
  }

  private YearMonth currentMonth() {
    return YearMonth.now(ZoneId.systemDefault());
  }
}
