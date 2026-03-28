package com.prosperity.shared;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;

class TransactionStateTest {

  @Test
  void enumHasExactlyThreeValues() {
    assertThat(TransactionState.values()).hasSize(3);
  }

  @Test
  void manualUnmatched_exists() {
    assertThat(TransactionState.valueOf("MANUAL_UNMATCHED"))
        .isEqualTo(TransactionState.MANUAL_UNMATCHED);
  }

  @Test
  void importedUnmatched_exists() {
    assertThat(TransactionState.valueOf("IMPORTED_UNMATCHED"))
        .isEqualTo(TransactionState.IMPORTED_UNMATCHED);
  }

  @Test
  void matched_exists() {
    assertThat(TransactionState.valueOf("MATCHED")).isEqualTo(TransactionState.MATCHED);
  }

  @Test
  void allValuesArePresent() {
    assertThat(TransactionState.values())
        .containsExactlyInAnyOrder(
            TransactionState.MANUAL_UNMATCHED,
            TransactionState.IMPORTED_UNMATCHED,
            TransactionState.MATCHED);
  }
}
