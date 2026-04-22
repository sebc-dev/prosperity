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
import com.prosperity.shared.RolloverPolicy;
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.sql.Date;
import java.time.LocalDate;
import java.time.YearMonth;
import java.util.ArrayList;
import java.util.Arrays;
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

/**
 * Business logic for envelope CRUD, scope derivation (D-07), D-01 category-uniqueness enforcement,
 * consumed aggregation, lazy rollover formula (D-12, 1-month lookback + zero-clamp), status
 * computation (D-13 thresholds), and hard-vs-soft delete (D-18).
 *
 * <p>All public methods accept {@code userEmail} from the controller layer and never touch
 * {@code SecurityContextHolder} directly. Access control mirrors {@code TransactionService} and
 * {@code AccountService}: 404 before 403 via {@code existsById} check.
 *
 * <p><b>D-13 ratio denominator:</b> {@code ratio = consumed / (effectiveBudget + carryOver)} — the
 * literal denominator is the allocatable total for the period, not the post-consumption signed
 * remainder. For RESET envelopes {@code carryOver = 0} so the denominator collapses to
 * {@code effectiveBudget}. When the allocatable total is zero or negative the ratio is defined as
 * {@code 0} (drives status to GREEN — defensive).
 */
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

  // ---------------------------------------------------------------------------
  // Public API
  // ---------------------------------------------------------------------------

  /**
   * Creates an envelope on an account. Scope is DERIVED server-side from the account's
   * {@link AccountType} (Pitfall 4): SHARED account -> scope = SHARED, owner = null; PERSONAL
   * account -> scope = PERSONAL, owner = current user. Enforces D-01 uniqueness of categories per
   * envelope per account.
   *
   * @throws AccountNotFoundException if the account does not exist (404)
   * @throws AccountAccessDeniedException if the user has no WRITE access (403)
   * @throws CategoryNotFoundException if any categoryId does not exist
   * @throws DuplicateEnvelopeCategoryException if any category is already linked to another
   *     non-archived envelope on the same account (409)
   */
  @Transactional
  public EnvelopeResponse createEnvelope(
      UUID accountId, CreateEnvelopeRequest request, String userEmail) {
    User user = resolveUser(userEmail);
    requireAccountAccess(accountId, user.getId(), AccessLevel.WRITE);

    Account account =
        accountRepository
            .findById(accountId)
            .orElseThrow(() -> new AccountNotFoundException("Account not found: " + accountId));

    Set<Category> loadedCategories = loadCategoriesOrThrow(request.categoryIds());

    for (UUID categoryId : request.categoryIds()) {
      if (envelopeRepository.existsCategoryLinkOnAccount(accountId, categoryId, null)) {
        throw new DuplicateEnvelopeCategoryException(
            "La categorie " + categoryId + " est deja liee a une autre enveloppe de ce compte");
      }
    }

    EnvelopeScope scope =
        account.getAccountType() == AccountType.SHARED
            ? EnvelopeScope.SHARED
            : EnvelopeScope.PERSONAL;
    User owner = scope == EnvelopeScope.PERSONAL ? user : null;

    Envelope envelope = new Envelope(account, request.name(), scope, new Money(request.budget()));
    envelope.setOwner(owner);
    envelope.setRolloverPolicy(request.rolloverPolicy());
    envelope.getCategories().addAll(loadedCategories);
    envelopeRepository.save(envelope);

    return toResponse(envelope, YearMonth.now());
  }

  /**
   * Lists envelopes on a single account accessible to the current user. Archived envelopes are
   * excluded by default; pass {@code includeArchived=true} to include them.
   *
   * @throws AccountNotFoundException if the account does not exist (404)
   * @throws AccountAccessDeniedException if the user has no READ access (403)
   */
  @Transactional(readOnly = true)
  public List<EnvelopeResponse> listEnvelopesForAccount(
      UUID accountId, boolean includeArchived, String userEmail) {
    User user = resolveUser(userEmail);
    requireAccountAccess(accountId, user.getId(), AccessLevel.READ);

    List<Envelope> envelopes;
    if (includeArchived) {
      envelopes =
          envelopeRepository.findAllAccessibleToUserIncludingArchived(user.getId()).stream()
              .filter(e -> e.getBankAccount().getId().equals(accountId))
              .toList();
    } else {
      envelopes = envelopeRepository.findByAccountAccessibleToUser(accountId, user.getId());
    }

    YearMonth now = YearMonth.now();
    return envelopes.stream().map(e -> toResponse(e, now)).toList();
  }

  /**
   * Lists all envelopes accessible to the current user across every account. Archived envelopes
   * are excluded by default; pass {@code includeArchived=true} to include them.
   */
  @Transactional(readOnly = true)
  public List<EnvelopeResponse> listAllEnvelopes(boolean includeArchived, String userEmail) {
    User user = resolveUser(userEmail);
    List<Envelope> envelopes =
        includeArchived
            ? envelopeRepository.findAllAccessibleToUserIncludingArchived(user.getId())
            : envelopeRepository.findAllAccessibleToUser(user.getId());
    YearMonth now = YearMonth.now();
    return envelopes.stream().map(e -> toResponse(e, now)).toList();
  }

  /**
   * Returns a single envelope (full EnvelopeResponse with consumed/available/ratio/status for the
   * current month).
   *
   * @throws EnvelopeNotFoundException if the envelope does not exist (404)
   * @throws AccountAccessDeniedException if the user has no READ access on the envelope's account
   */
  @Transactional(readOnly = true)
  public EnvelopeResponse getEnvelope(UUID envelopeId, String userEmail) {
    User user = resolveUser(userEmail);
    Envelope envelope = requireEnvelopeAccess(envelopeId, user.getId(), AccessLevel.READ);
    return toResponse(envelope, YearMonth.now());
  }

  /**
   * Partial PATCH on an envelope (Phase 3 D-08 convention). Only non-null fields are applied.
   * {@code categoryIds} (when non-null) REPLACES the whole category set via {@code clear()}+{@code
   * addAll()} — Pitfall 3 (never reassign a {@code @ManyToMany} collection). D-01 uniqueness is
   * re-validated excluding the envelope being updated.
   *
   * @throws EnvelopeNotFoundException if the envelope does not exist (404)
   * @throws AccountAccessDeniedException if the user has no WRITE access (403)
   * @throws CategoryNotFoundException if any categoryId does not exist
   * @throws DuplicateEnvelopeCategoryException if any new category is already linked to ANOTHER
   *     non-archived envelope on the same account
   */
  @Transactional
  public EnvelopeResponse updateEnvelope(
      UUID envelopeId, UpdateEnvelopeRequest request, String userEmail) {
    User user = resolveUser(userEmail);
    Envelope envelope = requireEnvelopeAccess(envelopeId, user.getId(), AccessLevel.WRITE);

    if (request.name() != null) {
      envelope.setName(request.name());
    }
    if (request.budget() != null) {
      envelope.setBudget(new Money(request.budget()));
    }
    if (request.rolloverPolicy() != null) {
      envelope.setRolloverPolicy(request.rolloverPolicy());
    }
    if (request.categoryIds() != null) {
      Set<Category> loadedCategories = loadCategoriesOrThrow(request.categoryIds());

      UUID accountId = envelope.getBankAccount().getId();
      for (UUID categoryId : request.categoryIds()) {
        if (envelopeRepository.existsCategoryLinkOnAccount(accountId, categoryId, envelopeId)) {
          throw new DuplicateEnvelopeCategoryException(
              "La categorie " + categoryId + " est deja liee a une autre enveloppe de ce compte");
        }
      }

      // Pitfall 3: mutate @ManyToMany collection in place, never reassign.
      envelope.getCategories().clear();
      envelope.getCategories().addAll(loadedCategories);
    }

    envelopeRepository.save(envelope);
    return toResponse(envelope, YearMonth.now());
  }

  /**
   * Hard-deletes when no EnvelopeAllocation exists, otherwise sets archived=true (D-18). Requires
   * WRITE access.
   *
   * @throws EnvelopeNotFoundException if the envelope does not exist (404)
   * @throws AccountAccessDeniedException if the user has no WRITE access (403)
   */
  @Transactional
  public void deleteEnvelope(UUID envelopeId, String userEmail) {
    User user = resolveUser(userEmail);
    Envelope envelope = requireEnvelopeAccess(envelopeId, user.getId(), AccessLevel.WRITE);

    if (envelopeRepository.hasAnyAllocation(envelopeId)) {
      envelope.setArchived(true);
      envelopeRepository.save(envelope);
    } else {
      envelopeRepository.delete(envelope);
    }
  }

  /**
   * Returns a 12-month history ending at {@code monthInclusive} (i.e. months
   * {@code [monthInclusive-11, monthInclusive]}). Each entry overlays monthly override (if any)
   * onto the default budget and computes consumed/available/ratio/status using the same formulas
   * as the current-month view.
   *
   * @throws EnvelopeNotFoundException if the envelope does not exist (404)
   * @throws AccountAccessDeniedException if the user has no READ access (403)
   */
  @Transactional(readOnly = true)
  public List<EnvelopeHistoryEntry> getEnvelopeHistory(
      UUID envelopeId, YearMonth monthInclusive, String userEmail) {
    User user = resolveUser(userEmail);
    Envelope envelope = requireEnvelopeAccess(envelopeId, user.getId(), AccessLevel.READ);

    YearMonth from = monthInclusive.minusMonths(11);
    LocalDate fromDate = from.atDay(1);
    LocalDate toDate = monthInclusive.plusMonths(1).atDay(1); // half-open upper bound

    UUID accountId = envelope.getBankAccount().getId();

    List<Object[]> rows =
        envelopeRepository.findMonthlyConsumptionRange(envelopeId, accountId, fromDate, toDate);

    List<EnvelopeAllocation> overrides =
        allocationRepository.findByEnvelopeIdAndMonthRange(envelopeId, fromDate, toDate);

    Map<YearMonth, BigDecimal> overrideByMonth = new HashMap<>();
    for (EnvelopeAllocation override : overrides) {
      overrideByMonth.put(override.getMonth(), override.getAllocatedAmount().amount());
    }

    Map<YearMonth, BigDecimal> consumedByMonth = new HashMap<>();
    for (Object[] row : rows) {
      LocalDate monthStart = extractLocalDate(row[0]);
      BigDecimal consumedValue = (BigDecimal) row[1];
      consumedByMonth.put(YearMonth.from(monthStart), consumedValue);
    }

    List<EnvelopeHistoryEntry> entries = new ArrayList<>(12);
    YearMonth cursor = from;
    for (int i = 0; i < 12; i++) {
      BigDecimal effective =
          overrideByMonth.getOrDefault(cursor, envelope.getBudget().amount());
      BigDecimal consumed = consumedByMonth.getOrDefault(cursor, BigDecimal.ZERO);
      BigDecimal carry = computeCarryOver(envelope, cursor);
      BigDecimal allocatable = effective.add(carry);
      BigDecimal available = allocatable.subtract(consumed);
      BigDecimal ratio = computeRatio(consumed, allocatable);
      EnvelopeStatus status = computeStatus(ratio);

      entries.add(new EnvelopeHistoryEntry(cursor, effective, consumed, available, ratio, status));

      cursor = cursor.plusMonths(1);
    }

    return entries;
  }

  // ---------------------------------------------------------------------------
  // Private helpers — access control
  // ---------------------------------------------------------------------------

  private void requireAccountAccess(UUID accountId, UUID userId, AccessLevel required) {
    if (!accountRepository.existsById(accountId)) {
      throw new AccountNotFoundException("Account not found: " + accountId);
    }
    List<AccessLevel> levels =
        Arrays.stream(AccessLevel.values()).filter(l -> l.isAtLeast(required)).toList();
    if (!accountRepository.hasAccess(accountId, userId, levels)) {
      throw new AccountAccessDeniedException("Access denied to account: " + accountId);
    }
  }

  private Envelope requireEnvelopeAccess(UUID envelopeId, UUID userId, AccessLevel required) {
    if (!envelopeRepository.existsById(envelopeId)) {
      throw new EnvelopeNotFoundException("Envelope not found: " + envelopeId);
    }
    Envelope envelope =
        envelopeRepository
            .findById(envelopeId)
            .orElseThrow(() -> new EnvelopeNotFoundException("Envelope not found: " + envelopeId));
    requireAccountAccess(envelope.getBankAccount().getId(), userId, required);
    return envelope;
  }

  private User resolveUser(String userEmail) {
    return userRepository
        .findByEmail(userEmail)
        .orElseThrow(() -> new UserNotFoundException("User not found: " + userEmail));
  }

  // ---------------------------------------------------------------------------
  // Private helpers — domain computation (D-12, D-13)
  // ---------------------------------------------------------------------------

  /**
   * Resolves the effective budget for a given month: monthly override (EnvelopeAllocation) if
   * present, else the envelope's default budget (D-08).
   */
  private Money resolveEffectiveBudget(Envelope envelope, YearMonth month) {
    return allocationRepository
        .findByEnvelopeIdAndMonthValue(envelope.getId(), month.atDay(1))
        .map(EnvelopeAllocation::getAllocatedAmount)
        .orElse(envelope.getBudget());
  }

  /** Sums consumed amount for a given month (non-negative BigDecimal). */
  private Money sumConsumed(Envelope envelope, YearMonth month) {
    LocalDate start = month.atDay(1);
    LocalDate next = month.plusMonths(1).atDay(1);
    BigDecimal raw =
        envelopeRepository.sumConsumedForMonth(
            envelope.getId(), envelope.getBankAccount().getId(), start, next);
    return new Money(raw == null ? BigDecimal.ZERO : raw);
  }

  /**
   * Computes carry-over from previous month (D-12 v1): RESET policy returns zero, CARRY_OVER
   * returns {@code max(0, prevEffectiveBudget - prevConsumed)}. Lookback is exactly 1 month (does
   * NOT chain back further).
   */
  private BigDecimal computeCarryOver(Envelope envelope, YearMonth month) {
    if (envelope.getRolloverPolicy() != RolloverPolicy.CARRY_OVER) {
      return BigDecimal.ZERO;
    }
    YearMonth prev = month.minusMonths(1);
    BigDecimal prevBudget = resolveEffectiveBudget(envelope, prev).amount();
    BigDecimal prevConsumed = sumConsumed(envelope, prev).amount();
    BigDecimal raw = prevBudget.subtract(prevConsumed);
    return raw.signum() > 0 ? raw : BigDecimal.ZERO;
  }

  /**
   * D-13 ratio: {@code consumed / allocatable} where {@code allocatable = effectiveBudget +
   * carryOver}. Returns {@code 0} when allocatable is null, zero, or negative (defensive — drives
   * status to GREEN).
   */
  private BigDecimal computeRatio(BigDecimal consumed, BigDecimal allocatable) {
    if (allocatable == null || allocatable.signum() <= 0) {
      return BigDecimal.ZERO;
    }
    return consumed.divide(allocatable, 4, RoundingMode.HALF_UP);
  }

  /**
   * D-13 status thresholds: ratio &lt; 0.80 -> GREEN; 0.80 &le; ratio &le; 1.00 -> YELLOW; ratio
   * &gt; 1.00 -> RED. Negative/null ratio returns GREEN defensively.
   */
  private EnvelopeStatus computeStatus(BigDecimal ratio) {
    if (ratio == null || ratio.signum() < 0) {
      return EnvelopeStatus.GREEN;
    }
    if (ratio.compareTo(RED_THRESHOLD) > 0) {
      return EnvelopeStatus.RED;
    }
    if (ratio.compareTo(YELLOW_THRESHOLD) >= 0) {
      return EnvelopeStatus.YELLOW;
    }
    return EnvelopeStatus.GREEN;
  }

  // ---------------------------------------------------------------------------
  // Private helpers — mapping
  // ---------------------------------------------------------------------------

  private Set<Category> loadCategoriesOrThrow(Set<UUID> categoryIds) {
    List<Category> loaded = categoryRepository.findAllById(categoryIds);
    if (loaded.size() != categoryIds.size()) {
      Set<UUID> foundIds =
          loaded.stream().map(Category::getId).collect(Collectors.toCollection(HashSet::new));
      List<UUID> missing =
          categoryIds.stream().filter(id -> !foundIds.contains(id)).toList();
      throw new CategoryNotFoundException("Categories introuvables : " + missing);
    }
    return new HashSet<>(loaded);
  }

  private EnvelopeResponse toResponse(Envelope envelope, YearMonth currentMonth) {
    Money effectiveBudget = resolveEffectiveBudget(envelope, currentMonth);
    Optional<EnvelopeAllocation> overrideOpt =
        allocationRepository.findByEnvelopeIdAndMonthValue(envelope.getId(), currentMonth.atDay(1));
    boolean hasOverride = overrideOpt.isPresent();
    Money consumed = sumConsumed(envelope, currentMonth);
    BigDecimal carryOver = computeCarryOver(envelope, currentMonth);
    BigDecimal allocatable = effectiveBudget.amount().add(carryOver);
    Money available = new Money(allocatable.subtract(consumed.amount()));
    BigDecimal ratio = computeRatio(consumed.amount(), allocatable);
    EnvelopeStatus status = computeStatus(ratio);

    List<EnvelopeResponse.EnvelopeCategoryRef> cats =
        envelope.getCategories().stream()
            .sorted(Comparator.comparing(Category::getName))
            .map(c -> new EnvelopeResponse.EnvelopeCategoryRef(c.getId(), c.getName()))
            .toList();

    return new EnvelopeResponse(
        envelope.getId(),
        envelope.getBankAccount().getId(),
        envelope.getBankAccount().getName(),
        envelope.getName(),
        envelope.getScope(),
        envelope.getOwner() == null ? null : envelope.getOwner().getId(),
        cats,
        envelope.getRolloverPolicy(),
        envelope.getBudget().amount(),
        effectiveBudget.amount(),
        consumed.amount(),
        available.amount(),
        ratio,
        status,
        hasOverride,
        envelope.isArchived(),
        envelope.getCreatedAt());
  }

  /**
   * Extracts a LocalDate from a native SQL row value. PostgreSQL's JDBC driver may return either
   * {@link java.sql.Date} or {@link LocalDate} depending on the driver version and type binding.
   */
  private LocalDate extractLocalDate(Object value) {
    if (value instanceof LocalDate localDate) {
      return localDate;
    }
    if (value instanceof Date sqlDate) {
      return sqlDate.toLocalDate();
    }
    throw new IllegalStateException(
        "Unexpected month_start value type: " + (value == null ? "null" : value.getClass()));
  }
}
