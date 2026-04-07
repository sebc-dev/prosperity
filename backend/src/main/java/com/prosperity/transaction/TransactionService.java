package com.prosperity.transaction;

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
import java.math.BigDecimal;
import java.util.Arrays;
import java.util.List;
import java.util.UUID;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * Service handling transaction business logic with access control.
 *
 * <p>All public methods accept {@code userEmail} from the controller layer. Access control enforces
 * the 403-vs-404 pattern from AccountService (D-10, D-11, D-12).
 */
@Service
public class TransactionService {

  private final TransactionRepository transactionRepository;
  private final TransactionSplitRepository transactionSplitRepository;
  private final CategoryRepository categoryRepository;
  private final AccountRepository accountRepository;
  private final UserRepository userRepository;

  public TransactionService(
      TransactionRepository transactionRepository,
      TransactionSplitRepository transactionSplitRepository,
      CategoryRepository categoryRepository,
      AccountRepository accountRepository,
      UserRepository userRepository) {
    this.transactionRepository = transactionRepository;
    this.transactionSplitRepository = transactionSplitRepository;
    this.categoryRepository = categoryRepository;
    this.accountRepository = accountRepository;
    this.userRepository = userRepository;
  }

  // ---------------------------------------------------------------------------
  // Public API
  // ---------------------------------------------------------------------------

  /**
   * Creates a manual transaction on an account. Requires WRITE access to the account.
   *
   * @throws AccountAccessDeniedException if user has no access (403)
   * @throws AccountNotFoundException if account does not exist (404)
   * @throws CategoryNotFoundException if categoryId is non-null and category does not exist
   */
  @Transactional
  public TransactionResponse createTransaction(
      UUID accountId, CreateTransactionRequest request, String userEmail) {
    User user = resolveUser(userEmail);
    requireAccountAccess(accountId, user.getId(), AccessLevel.WRITE);

    var account =
        accountRepository
            .findById(accountId)
            .orElseThrow(() -> new AccountNotFoundException("Account not found: " + accountId));

    Transaction transaction =
        new Transaction(account, new Money(request.amount()), request.transactionDate(),
            TransactionSource.MANUAL);
    transaction.setDescription(request.description());
    transaction.setCreatedBy(user);

    if (request.categoryId() != null) {
      Category category =
          categoryRepository
              .findById(request.categoryId())
              .orElseThrow(
                  () ->
                      new CategoryNotFoundException(
                          "Categorie introuvable : " + request.categoryId()));
      transaction.setCategory(category);
    }

    transactionRepository.save(transaction);
    return toResponse(transaction);
  }

  /**
   * Returns a paginated list of transactions for an account with optional filters. Requires READ
   * access.
   */
  @Transactional(readOnly = true)
  public Page<TransactionResponse> getTransactions(
      UUID accountId, TransactionFilterParams filters, Pageable pageable, String userEmail) {
    User user = resolveUser(userEmail);
    requireAccountAccess(accountId, user.getId(), AccessLevel.READ);

    Page<Transaction> page =
        transactionRepository.findByFilters(
            accountId,
            filters.dateFrom(),
            filters.dateTo(),
            filters.amountMin(),
            filters.amountMax(),
            filters.categoryId(),
            filters.search(),
            pageable);
    return page.map(this::toResponse);
  }

  /**
   * Returns a single transaction by id. Requires READ access to the transaction's account.
   *
   * @throws TransactionNotFoundException if transaction does not exist
   * @throws AccountAccessDeniedException if user has no access to the account (403)
   */
  @Transactional(readOnly = true)
  public TransactionResponse getTransaction(UUID transactionId, String userEmail) {
    User user = resolveUser(userEmail);
    Transaction transaction =
        transactionRepository
            .findById(transactionId)
            .orElseThrow(
                () ->
                    new TransactionNotFoundException(
                        "Transaction introuvable : " + transactionId));
    requireAccountAccess(transaction.getBankAccount().getId(), user.getId(), AccessLevel.READ);
    return toResponse(transaction);
  }

  /**
   * Updates a manual transaction's fields. Only MANUAL source transactions can be edited (D-02).
   * Requires WRITE access.
   *
   * @throws IllegalStateException if transaction source is not MANUAL
   */
  @Transactional
  public TransactionResponse updateTransaction(
      UUID transactionId, UpdateTransactionRequest request, String userEmail) {
    User user = resolveUser(userEmail);
    Transaction transaction =
        transactionRepository
            .findById(transactionId)
            .orElseThrow(
                () ->
                    new TransactionNotFoundException(
                        "Transaction introuvable : " + transactionId));

    if (transaction.getSource() != TransactionSource.MANUAL) {
      throw new IllegalStateException("Seules les transactions manuelles peuvent etre modifiees");
    }

    requireAccountAccess(transaction.getBankAccount().getId(), user.getId(), AccessLevel.WRITE);

    if (request.amount() != null) {
      transaction.setAmount(new Money(request.amount()));
    }
    if (request.transactionDate() != null) {
      transaction.setTransactionDate(request.transactionDate());
    }
    if (request.description() != null) {
      transaction.setDescription(request.description());
    }

    if (Boolean.TRUE.equals(request.clearCategory())) {
      transaction.setCategory(null);
    } else if (request.categoryId() != null) {
      Category category =
          categoryRepository
              .findById(request.categoryId())
              .orElseThrow(
                  () ->
                      new CategoryNotFoundException(
                          "Categorie introuvable : " + request.categoryId()));
      transaction.setCategory(category);
    }

    transactionRepository.save(transaction);
    return toResponse(transaction);
  }

  /**
   * Deletes a manual transaction. Only MANUAL source transactions can be deleted (D-03). Requires
   * WRITE access. Splits are deleted first.
   *
   * @throws IllegalStateException if transaction source is not MANUAL
   */
  @Transactional
  public void deleteTransaction(UUID transactionId, String userEmail) {
    User user = resolveUser(userEmail);
    Transaction transaction =
        transactionRepository
            .findById(transactionId)
            .orElseThrow(
                () ->
                    new TransactionNotFoundException(
                        "Transaction introuvable : " + transactionId));

    if (transaction.getSource() != TransactionSource.MANUAL) {
      throw new IllegalStateException("Seules les transactions manuelles peuvent etre supprimees");
    }

    requireAccountAccess(transaction.getBankAccount().getId(), user.getId(), AccessLevel.WRITE);

    transactionSplitRepository.deleteByTransactionId(transactionId);
    transactionRepository.delete(transaction);
  }

  /**
   * Toggles the pointed status of a transaction. Requires WRITE access (D-21).
   *
   * @throws TransactionNotFoundException if transaction does not exist
   */
  @Transactional
  public TransactionResponse togglePointed(UUID transactionId, String userEmail) {
    User user = resolveUser(userEmail);
    Transaction transaction =
        transactionRepository
            .findById(transactionId)
            .orElseThrow(
                () ->
                    new TransactionNotFoundException(
                        "Transaction introuvable : " + transactionId));
    requireAccountAccess(transaction.getBankAccount().getId(), user.getId(), AccessLevel.WRITE);
    transaction.setPointed(!transaction.isPointed());
    transactionRepository.save(transaction);
    return toResponse(transaction);
  }

  /**
   * Updates the category of a transaction. Pass null categoryId to clear the category. Requires
   * WRITE access to the account.
   *
   * @param transactionId the transaction to update
   * @param categoryId the new category, or null to clear
   * @param userEmail the authenticated user's email
   * @throws TransactionNotFoundException if the transaction does not exist
   * @throws CategoryNotFoundException if the categoryId is non-null and does not exist
   */
  @Transactional
  public void updateCategory(UUID transactionId, UUID categoryId, String userEmail) {
    User user = resolveUser(userEmail);
    Transaction transaction =
        transactionRepository
            .findById(transactionId)
            .orElseThrow(
                () ->
                    new TransactionNotFoundException("Transaction introuvable : " + transactionId));

    requireAccountAccess(transaction.getBankAccount().getId(), user.getId(), AccessLevel.WRITE);

    if (categoryId == null) {
      transaction.setCategory(null);
    } else {
      Category category =
          categoryRepository
              .findById(categoryId)
              .orElseThrow(
                  () -> new CategoryNotFoundException("Categorie introuvable : " + categoryId));
      transaction.setCategory(category);
    }
    transactionRepository.save(transaction);
  }

  /**
   * Sets (replaces) splits on a transaction. The sum of split amounts must equal the transaction
   * amount (D-05). The transaction category is set to null when splits are present (D-06). Requires
   * WRITE access.
   *
   * @throws IllegalArgumentException if split amounts do not sum to the transaction amount
   * @throws CategoryNotFoundException if any split's categoryId does not exist
   */
  @Transactional
  public TransactionResponse setSplits(
      UUID transactionId, List<TransactionSplitRequest> splits, String userEmail) {
    User user = resolveUser(userEmail);
    Transaction transaction =
        transactionRepository
            .findById(transactionId)
            .orElseThrow(
                () ->
                    new TransactionNotFoundException(
                        "Transaction introuvable : " + transactionId));
    requireAccountAccess(transaction.getBankAccount().getId(), user.getId(), AccessLevel.WRITE);

    BigDecimal splitSum =
        splits.stream()
            .map(TransactionSplitRequest::amount)
            .reduce(BigDecimal.ZERO, BigDecimal::add);
    if (splitSum.compareTo(transaction.getAmount().amount()) != 0) {
      throw new IllegalArgumentException(
          "La somme des splits ("
              + splitSum
              + ") ne correspond pas au montant de la transaction ("
              + transaction.getAmount().amount()
              + ")");
    }

    transactionSplitRepository.deleteByTransactionId(transactionId);
    transactionSplitRepository.flush();

    for (TransactionSplitRequest splitRequest : splits) {
      Category category =
          categoryRepository
              .findById(splitRequest.categoryId())
              .orElseThrow(
                  () ->
                      new CategoryNotFoundException(
                          "Categorie introuvable : " + splitRequest.categoryId()));
      TransactionSplit split =
          new TransactionSplit(transaction, category, new Money(splitRequest.amount()));
      split.setDescription(splitRequest.description());
      transactionSplitRepository.save(split);
    }

    transaction.setCategory(null);
    transactionRepository.save(transaction);
    return toResponse(transaction);
  }

  /**
   * Clears all splits from a transaction. Requires WRITE access.
   *
   * @throws TransactionNotFoundException if the transaction does not exist
   */
  @Transactional
  public TransactionResponse clearSplits(UUID transactionId, String userEmail) {
    User user = resolveUser(userEmail);
    Transaction transaction =
        transactionRepository
            .findById(transactionId)
            .orElseThrow(
                () ->
                    new TransactionNotFoundException(
                        "Transaction introuvable : " + transactionId));
    requireAccountAccess(transaction.getBankAccount().getId(), user.getId(), AccessLevel.WRITE);
    transactionSplitRepository.deleteByTransactionId(transactionId);
    return toResponse(transaction);
  }

  /**
   * Returns all splits for a transaction. Requires READ access.
   *
   * @throws TransactionNotFoundException if the transaction does not exist
   */
  @Transactional(readOnly = true)
  public List<TransactionSplitResponse> getSplits(UUID transactionId, String userEmail) {
    User user = resolveUser(userEmail);
    Transaction transaction =
        transactionRepository
            .findById(transactionId)
            .orElseThrow(
                () ->
                    new TransactionNotFoundException(
                        "Transaction introuvable : " + transactionId));
    requireAccountAccess(transaction.getBankAccount().getId(), user.getId(), AccessLevel.READ);
    return transactionSplitRepository.findByTransactionId(transactionId).stream()
        .map(this::toSplitResponse)
        .toList();
  }

  // ---------------------------------------------------------------------------
  // Private helpers
  // ---------------------------------------------------------------------------

  private User resolveUser(String userEmail) {
    return userRepository
        .findByEmail(userEmail)
        .orElseThrow(() -> new UserNotFoundException("User not found: " + userEmail));
  }

  /**
   * Checks that the user has at least the required access level on the account. Throws 403 if
   * account exists but user has no access. Throws 404 if account does not exist.
   */
  private void requireAccountAccess(UUID accountId, UUID userId, AccessLevel minimumLevel) {
    List<AccessLevel> allowedLevels =
        Arrays.stream(AccessLevel.values())
            .filter(l -> l.isAtLeast(minimumLevel))
            .toList();
    if (!accountRepository.hasAccess(accountId, userId, allowedLevels)) {
      if (accountRepository.existsById(accountId)) {
        throw new AccountAccessDeniedException("Access denied to account: " + accountId);
      }
      throw new AccountNotFoundException("Account not found: " + accountId);
    }
  }

  private TransactionResponse toResponse(Transaction transaction) {
    List<TransactionSplitResponse> splits =
        transactionSplitRepository.findByTransactionId(transaction.getId()).stream()
            .map(this::toSplitResponse)
            .toList();

    UUID categoryId = transaction.getCategory() != null ? transaction.getCategory().getId() : null;
    String categoryName =
        transaction.getCategory() != null ? transaction.getCategory().getName() : null;

    return new TransactionResponse(
        transaction.getId(),
        transaction.getBankAccount().getId(),
        transaction.getAmount().amount(),
        transaction.getDescription(),
        categoryId,
        categoryName,
        transaction.getTransactionDate(),
        transaction.getSource(),
        transaction.getState(),
        transaction.isPointed(),
        transaction.getCreatedAt(),
        splits);
  }

  private TransactionSplitResponse toSplitResponse(TransactionSplit split) {
    return new TransactionSplitResponse(
        split.getId(),
        split.getCategory().getId(),
        split.getCategory().getName(),
        split.getAmount().amount(),
        split.getDescription());
  }
}
