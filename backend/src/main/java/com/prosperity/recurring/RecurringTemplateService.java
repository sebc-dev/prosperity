package com.prosperity.recurring;

import com.prosperity.account.AccessLevel;
import com.prosperity.account.AccountAccessDeniedException;
import com.prosperity.account.AccountNotFoundException;
import com.prosperity.account.AccountRepository;
import com.prosperity.auth.User;
import com.prosperity.auth.UserNotFoundException;
import com.prosperity.auth.UserRepository;
import com.prosperity.category.Category;
import com.prosperity.category.CategoryNotFoundException;
import com.prosperity.category.CategoryRepository;
import com.prosperity.shared.Money;
import com.prosperity.shared.TransactionSource;
import com.prosperity.shared.TransactionState;
import com.prosperity.transaction.Transaction;
import com.prosperity.transaction.TransactionRepository;
import com.prosperity.transaction.TransactionResponse;
import java.time.LocalDate;
import java.util.Arrays;
import java.util.List;
import java.util.UUID;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * Business logic for recurring template CRUD and transaction generation.
 *
 * <p>All methods receive {@code userEmail} from the controller layer — this service never touches
 * {@code SecurityContextHolder} directly.
 */
@Service
public class RecurringTemplateService {

  private final RecurringTemplateRepository recurringTemplateRepository;
  private final TransactionRepository transactionRepository;
  private final AccountRepository accountRepository;
  private final CategoryRepository categoryRepository;
  private final UserRepository userRepository;

  public RecurringTemplateService(
      RecurringTemplateRepository recurringTemplateRepository,
      TransactionRepository transactionRepository,
      AccountRepository accountRepository,
      CategoryRepository categoryRepository,
      UserRepository userRepository) {
    this.recurringTemplateRepository = recurringTemplateRepository;
    this.transactionRepository = transactionRepository;
    this.accountRepository = accountRepository;
    this.categoryRepository = categoryRepository;
    this.userRepository = userRepository;
  }

  // ---------------------------------------------------------------------------
  // Public methods
  // ---------------------------------------------------------------------------

  /** Creates a new recurring template on the given account. Requires WRITE access. */
  @Transactional
  public RecurringTemplateResponse createTemplate(
      UUID accountId, CreateRecurringTemplateRequest request, String userEmail) {
    User user = resolveUser(userEmail);
    requireAccountAccess(accountId, user.getId(), AccessLevel.WRITE);

    var account =
        accountRepository
            .findById(accountId)
            .orElseThrow(() -> new AccountNotFoundException("Account not found: " + accountId));

    RecurringTemplate template =
        new RecurringTemplate(
            account, new Money(request.amount()), request.frequency(), request.nextDueDate());

    template.setDescription(request.description());
    template.setDayOfMonth(request.dayOfMonth());

    if (request.categoryId() != null) {
      Category category =
          categoryRepository
              .findById(request.categoryId())
              .orElseThrow(
                  () ->
                      new CategoryNotFoundException("Category not found: " + request.categoryId()));
      template.setCategory(category);
    }

    template.setCreatedBy(user);
    recurringTemplateRepository.save(template);

    return toResponse(template);
  }

  /**
   * Returns recurring templates for an account. Requires READ access. Pass {@code includeInactive}
   * to also return inactive templates.
   */
  @Transactional(readOnly = true)
  public List<RecurringTemplateResponse> getTemplates(
      UUID accountId, boolean includeInactive, String userEmail) {
    User user = resolveUser(userEmail);
    requireAccountAccess(accountId, user.getId(), AccessLevel.READ);

    List<RecurringTemplate> templates =
        includeInactive
            ? recurringTemplateRepository.findByBankAccountId(accountId)
            : recurringTemplateRepository.findByBankAccountIdAndActiveTrue(accountId);

    return templates.stream().map(this::toResponse).toList();
  }

  /**
   * Updates a recurring template's fields (partial update — all fields nullable). Requires WRITE
   * access on the template's account.
   */
  @Transactional
  public RecurringTemplateResponse updateTemplate(
      UUID templateId, UpdateRecurringTemplateRequest request, String userEmail) {
    User user = resolveUser(userEmail);

    RecurringTemplate template =
        recurringTemplateRepository
            .findById(templateId)
            .orElseThrow(
                () ->
                    new RecurringTemplateNotFoundException(
                        "Recurring template not found: " + templateId));

    requireAccountAccess(template.getBankAccount().getId(), user.getId(), AccessLevel.WRITE);

    if (request.amount() != null) {
      template.setAmount(new Money(request.amount()));
    }
    if (request.description() != null) {
      template.setDescription(request.description());
    }
    if (request.frequency() != null) {
      template.setFrequency(request.frequency());
    }
    if (request.dayOfMonth() != null) {
      template.setDayOfMonth(request.dayOfMonth());
    }
    if (request.nextDueDate() != null) {
      template.setNextDueDate(request.nextDueDate());
    }
    if (request.active() != null) {
      template.setActive(request.active());
    }

    if (Boolean.TRUE.equals(request.clearCategory())) {
      template.setCategory(null);
    } else if (request.categoryId() != null) {
      Category category =
          categoryRepository
              .findById(request.categoryId())
              .orElseThrow(
                  () ->
                      new CategoryNotFoundException("Category not found: " + request.categoryId()));
      template.setCategory(category);
    }

    recurringTemplateRepository.save(template);
    return toResponse(template);
  }

  /** Deletes a recurring template. Requires WRITE access on the template's account. */
  @Transactional
  public void deleteTemplate(UUID templateId, String userEmail) {
    User user = resolveUser(userEmail);

    RecurringTemplate template =
        recurringTemplateRepository
            .findById(templateId)
            .orElseThrow(
                () ->
                    new RecurringTemplateNotFoundException(
                        "Recurring template not found: " + templateId));

    requireAccountAccess(template.getBankAccount().getId(), user.getId(), AccessLevel.WRITE);

    recurringTemplateRepository.delete(template);
  }

  /**
   * Generates a real transaction from a recurring template. Sets source=RECURRING and advances
   * nextDueDate. Requires WRITE access on the template's account. Throws when the template is
   * inactive.
   */
  @Transactional
  public TransactionResponse generateTransaction(UUID templateId, String userEmail) {
    User user = resolveUser(userEmail);

    RecurringTemplate template =
        recurringTemplateRepository
            .findById(templateId)
            .orElseThrow(
                () ->
                    new RecurringTemplateNotFoundException(
                        "Recurring template not found: " + templateId));

    requireAccountAccess(template.getBankAccount().getId(), user.getId(), AccessLevel.WRITE);

    if (!template.isActive()) {
      throw new IllegalStateException("Le template est inactif");
    }

    Transaction transaction =
        new Transaction(
            template.getBankAccount(),
            template.getAmount(),
            template.getNextDueDate(),
            TransactionSource.RECURRING);

    transaction.setDescription(template.getDescription());
    transaction.setCategory(template.getCategory());
    transaction.setCreatedBy(user);
    transaction.setState(TransactionState.MANUAL_UNMATCHED);

    transactionRepository.save(transaction);

    template.setNextDueDate(advanceNextDueDate(template));
    recurringTemplateRepository.save(template);

    return new TransactionResponse(
        transaction.getId(),
        transaction.getBankAccount().getId(),
        transaction.getAmount().amount(),
        transaction.getDescription(),
        transaction.getCategory() != null ? transaction.getCategory().getId() : null,
        transaction.getCategory() != null ? transaction.getCategory().getName() : null,
        transaction.getTransactionDate(),
        transaction.getSource(),
        transaction.getState(),
        transaction.isPointed(),
        transaction.getCreatedAt(),
        List.of());
  }

  // ---------------------------------------------------------------------------
  // Private helpers
  // ---------------------------------------------------------------------------

  private User resolveUser(String email) {
    return userRepository
        .findByEmail(email)
        .orElseThrow(() -> new UserNotFoundException("User not found: " + email));
  }

  private void requireAccountAccess(UUID accountId, UUID userId, AccessLevel minimumLevel) {
    List<AccessLevel> allowedLevels =
        Arrays.stream(AccessLevel.values()).filter(l -> l.isAtLeast(minimumLevel)).toList();
    if (!accountRepository.hasAccess(accountId, userId, allowedLevels)) {
      if (accountRepository.existsById(accountId)) {
        throw new AccountAccessDeniedException("Access denied to account: " + accountId);
      }
      throw new AccountNotFoundException("Account not found: " + accountId);
    }
  }

  private RecurringTemplateResponse toResponse(RecurringTemplate t) {
    return new RecurringTemplateResponse(
        t.getId(),
        t.getBankAccount().getId(),
        t.getAmount().amount(),
        t.getDescription(),
        t.getCategory() != null ? t.getCategory().getId() : null,
        t.getCategory() != null ? t.getCategory().getName() : null,
        t.getFrequency(),
        t.getDayOfMonth(),
        t.getNextDueDate(),
        t.isActive(),
        t.getCreatedAt());
  }

  private LocalDate advanceNextDueDate(RecurringTemplate template) {
    LocalDate current = template.getNextDueDate();
    return switch (template.getFrequency()) {
      case WEEKLY -> current.plusWeeks(1);
      case MONTHLY ->
          template.getDayOfMonth() != null
              ? current
                  .plusMonths(1)
                  .withDayOfMonth(
                      Math.min(template.getDayOfMonth(), current.plusMonths(1).lengthOfMonth()))
              : current.plusMonths(1);
      case YEARLY -> current.plusYears(1);
    };
  }
}
