package com.prosperity.category;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.Table;
import java.time.Instant;
import java.util.UUID;

/** JPA entity representing a transaction category with optional hierarchical parent. */
@Entity
@Table(name = "categories")
public class Category {

  @Id
  @GeneratedValue(strategy = GenerationType.UUID)
  private UUID id;

  @Column(nullable = false, length = 100)
  private String name;

  @ManyToOne
  @JoinColumn(name = "parent_id")
  private Category parent;

  @Column(name = "plaid_category_id", length = 255)
  private String plaidCategoryId;

  @Column(name = "created_at", nullable = false, columnDefinition = "TIMESTAMPTZ")
  private Instant createdAt;

  protected Category() {}

  public Category(String name) {
    this.name = name;
    this.createdAt = Instant.now();
  }

  public UUID getId() {
    return id;
  }

  public void setId(UUID id) {
    this.id = id;
  }

  public String getName() {
    return name;
  }

  public void setName(String name) {
    this.name = name;
  }

  public Category getParent() {
    return parent;
  }

  public void setParent(Category parent) {
    this.parent = parent;
  }

  public String getPlaidCategoryId() {
    return plaidCategoryId;
  }

  public void setPlaidCategoryId(String plaidCategoryId) {
    this.plaidCategoryId = plaidCategoryId;
  }

  public Instant getCreatedAt() {
    return createdAt;
  }

  public void setCreatedAt(Instant createdAt) {
    this.createdAt = createdAt;
  }
}
