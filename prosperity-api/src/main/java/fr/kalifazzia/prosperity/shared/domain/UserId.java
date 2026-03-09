package fr.kalifazzia.prosperity.shared.domain;

import com.fasterxml.uuid.Generators;

import java.util.Objects;
import java.util.UUID;

/**
 * Value object wrapping a UUID for user identity.
 * Uses UUIDv7 (time-ordered epoch) for new IDs.
 */
public final class UserId {

    private final UUID value;

    private UserId(UUID value) {
        this.value = Objects.requireNonNull(value, "value must not be null");
    }

    /**
     * Generate a new UserId using UUIDv7 (time-ordered epoch).
     */
    public static UserId generate() {
        return new UserId(Generators.timeBasedEpochGenerator().generate());
    }

    /**
     * Create a UserId from an existing UUID.
     */
    public static UserId of(UUID value) {
        return new UserId(value);
    }

    /**
     * Create a UserId from a string representation.
     */
    public static UserId of(String value) {
        return new UserId(UUID.fromString(value));
    }

    public UUID getValue() {
        return value;
    }

    @Override
    public boolean equals(Object o) {
        if (this == o) return true;
        if (o == null || getClass() != o.getClass()) return false;
        UserId userId = (UserId) o;
        return value.equals(userId.value);
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
