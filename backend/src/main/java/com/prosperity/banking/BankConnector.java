package com.prosperity.banking;

import java.time.LocalDate;
import java.util.List;

/**
 * Abstract bank connector interface (D-03). Plaid is the initial implementation, but this interface
 * allows swapping to Powens, Salt Edge, or any other provider.
 */
public interface BankConnector {

  List<BankTransaction> fetchTransactions(String accessToken, LocalDate from, LocalDate to);

  String createLinkToken(String userId);
}
