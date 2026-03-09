package fr.kalifazzia.prosperity.category;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EntityListeners;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import org.springframework.data.annotation.CreatedDate;
import org.springframework.data.annotation.LastModifiedDate;
import org.springframework.data.jpa.domain.support.AuditingEntityListener;

import java.time.Instant;
import java.util.UUID;

@Entity
@Table(name = "categories")
@EntityListeners(AuditingEntityListener.class)
public class Category {

    @Id
    @Column(name = "id", updatable = false, nullable = false)
    private UUID id;

    @Column(name = "name_key", nullable = false, length = 100)
    private String nameKey;

    @Column(name = "icon", length = 50)
    private String icon;

    @Column(name = "is_default")
    private boolean isDefault;

    @Column(name = "created_by")
    private UUID createdBy;

    @CreatedDate
    @Column(name = "created_at", nullable = false, updatable = false)
    private Instant createdAt;

    @LastModifiedDate
    @Column(name = "updated_at", nullable = false)
    private Instant updatedAt;

    protected Category() {
    }

    public Category(UUID id, String nameKey, String icon, boolean isDefault, UUID createdBy) {
        this.id = id;
        this.nameKey = nameKey;
        this.icon = icon;
        this.isDefault = isDefault;
        this.createdBy = createdBy;
    }

    public UUID getId() {
        return id;
    }

    public String getNameKey() {
        return nameKey;
    }

    public String getIcon() {
        return icon;
    }

    public boolean isDefault() {
        return isDefault;
    }

    public UUID getCreatedBy() {
        return createdBy;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }

    public Instant getUpdatedAt() {
        return updatedAt;
    }
}
