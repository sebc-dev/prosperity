package fr.kalifazzia.prosperity.account;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.UniqueConstraint;

import java.util.UUID;

@Entity
@Table(name = "account_permissions", uniqueConstraints = {
        @UniqueConstraint(columnNames = {"account_id", "user_id"})
})
public class AccountPermission {

    @Id
    @Column(name = "id", updatable = false, nullable = false)
    private UUID id;

    @Column(name = "account_id", nullable = false)
    private UUID accountId;

    @Column(name = "user_id", nullable = false)
    private UUID userId;

    @Enumerated(EnumType.STRING)
    @Column(name = "permission_level", nullable = false)
    private PermissionLevel permissionLevel;

    protected AccountPermission() {
    }

    public AccountPermission(UUID id, UUID accountId, UUID userId, PermissionLevel permissionLevel) {
        this.id = id;
        this.accountId = accountId;
        this.userId = userId;
        this.permissionLevel = permissionLevel;
    }

    public UUID getId() {
        return id;
    }

    public UUID getAccountId() {
        return accountId;
    }

    public UUID getUserId() {
        return userId;
    }

    public PermissionLevel getPermissionLevel() {
        return permissionLevel;
    }
}
