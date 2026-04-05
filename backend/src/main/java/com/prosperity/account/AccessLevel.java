package com.prosperity.account;

/** Access level for a user on a bank account. */
public enum AccessLevel {
  READ,
  WRITE,
  ADMIN;

  /**
   * Returns true if this access level is at least the required level. Ordering: READ &lt; WRITE
   * &lt; ADMIN.
   */
  public boolean isAtLeast(AccessLevel required) {
    return this.ordinal() >= required.ordinal();
  }
}
