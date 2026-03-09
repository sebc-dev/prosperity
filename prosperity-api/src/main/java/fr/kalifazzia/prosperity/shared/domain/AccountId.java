package fr.kalifazzia.prosperity.shared.domain;

import com.fasterxml.uuid.Generators;

import java.util.Objects;
import java.util.UUID;

/**
 * Value object wrapping a UUID for account identity.
 * Uses UUIDv7 (time-ordered epoch) for new IDs.
 */
public final class AccountId {

    private final UUID value;

    private AccountId(UUID value) {
        this.value = Objects.requireNonNull(value, "value must not be null");
    }

    /**
     * Generate a new AccountId using UUIDv7 (time-ordered epoch).
     */
    public static AccountId generate() {
        return new AccountId(Generators.timeBasedEpochGenerator().generate());
    }

    /**
     * Create an AccountId from an existing UUID.
     */
    public static AccountId of(UUID value) {
        return new AccountId(value);
    }

    /**
     * Create an AccountId from a string representation.
     */
    public static AccountId of(String value) {
        return new AccountId(UUID.fromString(value));
    }

    public UUID getValue() {
        return value;
    }

    @Override
    public boolean equals(Object o) {
        if (this == o) return true;
        if (o == null || getClass() != o.getClass()) return false;
        AccountId accountId = (AccountId) o;
        return value.equals(accountId.value);
    }

    @Override
    public int hashCode() {
        return value.hashCode();
    }

    @Override
    public String toString() {
        return value.toString();
    }
}
