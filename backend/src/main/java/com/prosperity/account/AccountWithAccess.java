package com.prosperity.account;

/**
 * Projection record combining an Account entity with the current user's access level.
 * Used by JPQL constructor expressions to avoid untyped Object[] projections.
 */
public record AccountWithAccess(Account account, AccessLevel accessLevel) {}
