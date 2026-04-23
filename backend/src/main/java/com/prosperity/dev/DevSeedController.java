package com.prosperity.dev;

import com.prosperity.account.AccessLevel;
import com.prosperity.account.Account;
import com.prosperity.account.AccountAccess;
import com.prosperity.account.AccountAccessRepository;
import com.prosperity.account.AccountRepository;
import com.prosperity.auth.Role;
import com.prosperity.auth.User;
import com.prosperity.auth.UserRepository;
import com.prosperity.category.Category;
import com.prosperity.category.CategoryRepository;
import com.prosperity.envelope.Envelope;
import com.prosperity.envelope.EnvelopeAllocation;
import com.prosperity.envelope.EnvelopeAllocationRepository;
import com.prosperity.envelope.EnvelopeRepository;
import com.prosperity.shared.AccountType;
import com.prosperity.shared.EnvelopeScope;
import com.prosperity.shared.Money;
import com.prosperity.shared.RolloverPolicy;
import com.prosperity.shared.TransactionSource;
import com.prosperity.transaction.Transaction;
import com.prosperity.transaction.TransactionRepository;
import jakarta.persistence.EntityManager;
import java.time.LocalDate;
import java.time.YearMonth;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.springframework.context.annotation.Profile;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * Dev-only endpoint to wipe the database and load a deterministic demo dataset. Exposed only when
 * the "dev" Spring profile is active; absent in prod builds.
 */
@Profile("dev")
@RestController
@RequestMapping("/api/dev")
public class DevSeedController {

  // Deterministic category UUIDs from V011__seed_plaid_categories.sql.
  private static final UUID CAT_COURSES = UUID.fromString("a0000000-0000-0000-0000-000000000101");
  private static final UUID CAT_RESTAURANT =
      UUID.fromString("a0000000-0000-0000-0000-000000000102");
  private static final UUID CAT_CAFE = UUID.fromString("a0000000-0000-0000-0000-000000000103");
  private static final UUID CAT_CARBURANT =
      UUID.fromString("a0000000-0000-0000-0000-000000000201");
  private static final UUID CAT_TRANSIT = UUID.fromString("a0000000-0000-0000-0000-000000000202");
  private static final UUID CAT_LOYER = UUID.fromString("a0000000-0000-0000-0000-000000000301");
  private static final UUID CAT_ELEC = UUID.fromString("a0000000-0000-0000-0000-000000000302");
  private static final UUID CAT_INTERNET = UUID.fromString("a0000000-0000-0000-0000-000000000303");

  private final EntityManager em;
  private final UserRepository userRepository;
  private final AccountRepository accountRepository;
  private final AccountAccessRepository accountAccessRepository;
  private final CategoryRepository categoryRepository;
  private final TransactionRepository transactionRepository;
  private final EnvelopeRepository envelopeRepository;
  private final EnvelopeAllocationRepository envelopeAllocationRepository;
  private final PasswordEncoder passwordEncoder;

  public DevSeedController(
      EntityManager em,
      UserRepository userRepository,
      AccountRepository accountRepository,
      AccountAccessRepository accountAccessRepository,
      CategoryRepository categoryRepository,
      TransactionRepository transactionRepository,
      EnvelopeRepository envelopeRepository,
      EnvelopeAllocationRepository envelopeAllocationRepository,
      PasswordEncoder passwordEncoder) {
    this.em = em;
    this.userRepository = userRepository;
    this.accountRepository = accountRepository;
    this.accountAccessRepository = accountAccessRepository;
    this.categoryRepository = categoryRepository;
    this.transactionRepository = transactionRepository;
    this.envelopeRepository = envelopeRepository;
    this.envelopeAllocationRepository = envelopeAllocationRepository;
    this.passwordEncoder = passwordEncoder;
  }

  @PostMapping("/reset-and-seed")
  @Transactional
  public Map<String, Object> resetAndSeed() {
    reset();
    return seed();
  }

  private void reset() {
    // TRUNCATE in one call with CASCADE handles FK order. RESTART IDENTITY resets serials
    // (none here but cheap). System-seeded categories and flyway_schema_history are preserved.
    em.createNativeQuery(
            "TRUNCATE envelope_allocations, envelopes, envelope_categories,"
                + " transaction_splits, transactions, recurring_templates,"
                + " account_access, bank_accounts, users, spring_session,"
                + " spring_session_attributes RESTART IDENTITY CASCADE")
        .executeUpdate();
    em.flush();
  }

  private Map<String, Object> seed() {
    // User
    User user = new User("demo@prosperity.local", passwordEncoder.encode("demo1234"), "Demo");
    user.setRole(Role.ADMIN);
    userRepository.save(user);

    // Accounts
    Account personal = new Account("Compte courant", AccountType.PERSONAL);
    personal.setBalance(Money.of("2500.00"));
    accountRepository.save(personal);
    accountAccessRepository.save(new AccountAccess(user, personal, AccessLevel.WRITE));

    Account shared = new Account("Depenses maison", AccountType.SHARED);
    shared.setBalance(Money.of("1500.00"));
    accountRepository.save(shared);
    accountAccessRepository.save(new AccountAccess(user, shared, AccessLevel.WRITE));

    // Categories (must exist from V011)
    Category courses = categoryRepository.findById(CAT_COURSES).orElseThrow();
    Category restaurant = categoryRepository.findById(CAT_RESTAURANT).orElseThrow();
    Category cafe = categoryRepository.findById(CAT_CAFE).orElseThrow();
    Category carburant = categoryRepository.findById(CAT_CARBURANT).orElseThrow();
    Category transit = categoryRepository.findById(CAT_TRANSIT).orElseThrow();
    Category loyer = categoryRepository.findById(CAT_LOYER).orElseThrow();
    Category elec = categoryRepository.findById(CAT_ELEC).orElseThrow();
    Category internet = categoryRepository.findById(CAT_INTERNET).orElseThrow();

    // Transactions — 3 months of activity to feed statuses and history.
    YearMonth m0 = YearMonth.now(); // current month
    YearMonth m1 = m0.minusMonths(1);
    YearMonth m2 = m0.minusMonths(2);

    int txCount = 0;
    // Current month on personal account: courses ~420€, restaurant ~85€, carburant ~65€
    txCount += addTx(personal, user, courses, m0.atDay(3), "-48.20", "Carrefour");
    txCount += addTx(personal, user, courses, m0.atDay(10), "-62.50", "Monoprix");
    txCount += addTx(personal, user, courses, m0.atDay(17), "-145.80", "Auchan");
    txCount += addTx(personal, user, courses, m0.atDay(20), "-38.10", "Picard");
    txCount += addTx(personal, user, courses, m0.atDay(22), "-125.40", "Marche bio");
    txCount += addTx(personal, user, restaurant, m0.atDay(8), "-42.00", "Le Petit Bistro");
    txCount += addTx(personal, user, restaurant, m0.atDay(15), "-28.50", "Sushi Shop");
    txCount += addTx(personal, user, restaurant, m0.atDay(21), "-14.80", "Boulangerie");
    txCount += addTx(personal, user, cafe, m0.atDay(5), "-4.50", "Starbucks");
    txCount += addTx(personal, user, cafe, m0.atDay(12), "-3.80", "Cafe du coin");
    txCount += addTx(personal, user, carburant, m0.atDay(7), "-65.30", "Total Energies");

    // Current month on shared account: loyer 900€, elec 120€, internet 45€, transit 75€
    txCount += addTx(shared, user, loyer, m0.atDay(2), "-900.00", "Loyer appartement");
    txCount += addTx(shared, user, elec, m0.atDay(10), "-118.40", "EDF");
    txCount += addTx(shared, user, internet, m0.atDay(5), "-44.99", "Free Mobile");
    txCount += addTx(shared, user, transit, m0.atDay(6), "-75.20", "RATP Navigo");

    // Previous month — mixed, helps CARRY_OVER envelope show rollover.
    txCount += addTx(personal, user, courses, m1.atDay(8), "-82.00", "Auchan");
    txCount += addTx(personal, user, courses, m1.atDay(18), "-64.30", "Monoprix");
    txCount += addTx(personal, user, restaurant, m1.atDay(12), "-55.00", "Le Relais");
    txCount += addTx(personal, user, restaurant, m1.atDay(26), "-38.20", "Pizza Hut");
    txCount += addTx(personal, user, carburant, m1.atDay(3), "-72.00", "Total Energies");
    txCount += addTx(shared, user, loyer, m1.atDay(2), "-900.00", "Loyer appartement");
    txCount += addTx(shared, user, elec, m1.atDay(10), "-112.80", "EDF");
    txCount += addTx(shared, user, internet, m1.atDay(5), "-44.99", "Free Mobile");

    // Two months ago — history depth.
    txCount += addTx(personal, user, courses, m2.atDay(9), "-145.00", "Carrefour");
    txCount += addTx(personal, user, restaurant, m2.atDay(15), "-62.00", "Le Bistrot");
    txCount += addTx(shared, user, loyer, m2.atDay(2), "-900.00", "Loyer appartement");
    txCount += addTx(shared, user, elec, m2.atDay(10), "-125.50", "EDF");

    // Envelopes — 3 envelopes exercising GREEN / YELLOW / RED, RESET vs CARRY_OVER.
    Envelope envCourses =
        new Envelope(personal, "Courses", EnvelopeScope.PERSONAL, Money.of("500.00"));
    envCourses.getCategories().add(courses);
    envelopeRepository.save(envCourses);

    Envelope envRestaurant =
        new Envelope(personal, "Sorties", EnvelopeScope.PERSONAL, Money.of("150.00"));
    envRestaurant.setRolloverPolicy(RolloverPolicy.CARRY_OVER);
    envRestaurant.getCategories().add(restaurant);
    envRestaurant.getCategories().add(cafe);
    envelopeRepository.save(envRestaurant);

    Envelope envTransport =
        new Envelope(personal, "Transport", EnvelopeScope.PERSONAL, Money.of("120.00"));
    envTransport.getCategories().add(carburant);
    envTransport.getCategories().add(transit);
    envelopeRepository.save(envTransport);

    Envelope envLogement =
        new Envelope(shared, "Charges fixes", EnvelopeScope.SHARED, Money.of("1100.00"));
    envLogement.getCategories().add(loyer);
    envLogement.getCategories().add(elec);
    envLogement.getCategories().add(internet);
    envelopeRepository.save(envLogement);

    // Monthly allocation override on the Courses envelope for current month (600 instead of 500).
    envelopeAllocationRepository.save(
        new EnvelopeAllocation(envCourses, m0, Money.of("600.00")));

    Map<String, Object> summary = new LinkedHashMap<>();
    summary.put("user", "demo@prosperity.local");
    summary.put("password", "demo1234");
    summary.put("accountsCreated", 2);
    summary.put("transactionsCreated", txCount);
    summary.put("envelopesCreated", 4);
    summary.put("allocationsCreated", 1);
    summary.put("months", List.of(m2.toString(), m1.toString(), m0.toString()));
    return summary;
  }

  private int addTx(
      Account account,
      User createdBy,
      Category category,
      LocalDate date,
      String amount,
      String description) {
    Transaction t = new Transaction(account, Money.of(amount), date, TransactionSource.MANUAL);
    t.setDescription(description);
    t.setCategory(category);
    t.setCreatedBy(createdBy);
    transactionRepository.save(t);
    return 1;
  }
}
