# Phase 4: Categories - Research

**Researched:** 2026-04-05
**Domain:** Hierarchical category CRUD (backend + frontend), Flyway seed data, PrimeNG TreeSelect
**Confidence:** HIGH

## Summary

Phase 4 introduces a hierarchical category system with two types: system categories (seeded from a curated Plaid-aligned taxonomy) and user-created custom categories. The backend follows the established layered-by-feature pattern from Phase 3 (Controller/Service/Repository/DTOs in `com.prosperity.category`). The frontend mirrors the accounts module pattern: a dedicated page with `p-table`, a `p-dialog` for create/edit, and a shared `CategorySelector` component using PrimeNG `p-treeselect` for reuse in Phase 5 and 6.

The existing `Category` entity and `categories` table from Phase 1 provide the foundation. Two additions are needed: (1) an `is_system` boolean column via Flyway migration V010, and (2) a seed migration V011 inserting ~20-30 curated categories mapped to Plaid's Personal Finance Categories v2 taxonomy. The `PATCH /api/transactions/{id}/category` endpoint is backend-only in Phase 4 (no UI -- that comes in Phase 5).

**Primary recommendation:** Follow the Phase 3 pattern exactly (Controller/Service/Repository/DTOs as Java records, frontend signals + OnPush, `p-table` + `p-dialog`), add `is_system` via ALTER TABLE, seed categories via Flyway, and build the shared `CategorySelector` with `p-treeselect` in `frontend/src/app/shared/`.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** Categories are global to the household -- no `user_id`. Entity `Category.java` is already correct.
- **D-02:** Plaid categories seeded via Flyway migration (V010 or next). Curated set of ~20-30 categories for a French household. Hierarchical 2 levels (parent/child). `plaid_category_id` populated for Plaid-mapped categories.
- **D-03:** Plaid categories are read-only in UI. Distinction via `is_system BOOLEAN NOT NULL DEFAULT FALSE` added via migration.
- **D-04:** User can create custom categories as root or child of existing (Plaid or custom). Max depth: 2 levels. No arbitrary recursion.
- **D-05:** User can rename and delete custom categories. Delete blocked if category used by transactions (409 Conflict).
- **D-06:** `PATCH /api/transactions/{id}/category` implemented in Phase 4. Body: `{"categoryId": "uuid"}`. No UI -- tested via integration test only.
- **D-07:** Page `/categories` with `p-table` (Nom, Categorie parente, Type, Actions). Sort on Nom.
- **D-08:** Create/edit via `p-dialog`. Form: name + optional parent selector.
- **D-09:** Plaid categories read-only in table (no edit/delete buttons). Badge/icon distinction.
- **D-10:** Shared `CategorySelector` component using `p-treeselect` for reuse in Phase 5/6.

### Claude's Discretion
- Exact REST endpoint naming
- Exact DTO structure (Java records)
- Choice between `p-select` and `p-treeSelect` for selector (D-10 specifies `p-treeSelect`)
- Tailwind/PrimeNG badge styles for Plaid/Custom
- Exact `plaid_category_id` format in migration

### Deferred Ideas (OUT OF SCOPE)
- CATG-05: Automatic categorization rules
- CATG-06: History-based category suggestions
- Import/export categories (CSV/JSON)
- Color-coded/icon categories (Phase 10 dashboard)
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| CATG-01 | Plaid-imported transactions arrive with Plaid categories pre-filled | Seed migration V011 populates categories with `plaid_category_id` matching Plaid PFCv2 taxonomy. `PATCH /api/transactions/{id}/category` endpoint enables category assignment. |
| CATG-02 | User can change a transaction's category | `PATCH /api/transactions/{id}/category` with `{"categoryId":"uuid"}`. Backend-only in Phase 4, integration test validates. |
| CATG-03 | User can create custom categories | Full CRUD backend (POST/PUT/DELETE `/api/categories`) + frontend dialog with `p-dialog` form. `is_system=false` for custom categories. |
| CATG-04 | Categories are hierarchical (parent/sub-category) | 2-level hierarchy via `parent_id` self-referential FK (already in V004). TreeSelect component displays hierarchy. Parent selector filters to root-only categories. |
</phase_requirements>

## Standard Stack

### Core (already in project)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Spring Boot | 4.0.x | Backend framework | Already established in Phase 1-3 |
| Spring Data JPA | 4.0.x | ORM / Repository | Derived queries for category lookups |
| Flyway | 11.x | DB migrations | V010 (alter table) + V011 (seed data) |
| Angular | 21.x | Frontend SPA | Established in Phase 1-3 |
| PrimeNG | 21.1.4 | UI components | p-table, p-dialog, p-treeselect, p-tag |

### Supporting (no new dependencies)
No new backend or frontend dependencies are needed. All required PrimeNG components (`TreeSelectModule`, `TagModule`, `ConfirmDialogModule`) are already available in the installed PrimeNG 21.1.4 package.

## Architecture Patterns

### Backend Package Structure
```
backend/src/main/java/com/prosperity/category/
  Category.java              # Entity (existing, add isSystem field)
  CategoryRepository.java    # Repository (existing, add query methods)
  CategoryService.java       # NEW: business logic
  CategoryController.java    # NEW: REST endpoints
  CategoryResponse.java      # NEW: DTO record
  CreateCategoryRequest.java # NEW: DTO record
  UpdateCategoryRequest.java # NEW: DTO record
  CategoryNotFoundException.java  # NEW: exception
```

```
backend/src/main/java/com/prosperity/transaction/
  TransactionRepository.java  # Add existsByCategoryId query
  TransactionController.java  # NEW (minimal): PATCH /{id}/category only
  TransactionService.java     # NEW (minimal): updateCategory method only
  UpdateTransactionCategoryRequest.java  # NEW: DTO record
  TransactionNotFoundException.java      # NEW: exception
```

### Frontend Structure
```
frontend/src/app/
  shared/
    category-selector.ts       # NEW: shared CategorySelector component
    category-selector.spec.ts  # NEW: tests
  categories/
    categories.ts              # NEW: list page component
    categories.spec.ts         # NEW: tests
    category-dialog.ts         # NEW: create/edit dialog
    category-dialog.spec.ts    # NEW: tests
    category.service.ts        # NEW: HTTP service
    category.service.spec.ts   # NEW: tests
    category.types.ts          # NEW: TypeScript interfaces
```

### Pattern 1: Controller/Service/Repository (same as Phase 3)
**What:** Layered architecture per feature package
**When to use:** Every feature in this project
**Example:**
```java
// CategoryController.java -- HTTP concerns only
@RestController
@RequestMapping("/api/categories")
public class CategoryController {
  private final CategoryService categoryService;
  // ...
  @GetMapping
  public ResponseEntity<List<CategoryResponse>> list() {
    return ResponseEntity.ok(categoryService.getAllCategories());
  }
}
```

### Pattern 2: Java Records for DTOs (same as Phase 3)
**What:** Immutable DTOs with validation annotations
**Example:**
```java
public record CreateCategoryRequest(
    @NotBlank @Size(max = 100) String name,
    UUID parentId  // nullable -- null means root category
) {}

public record CategoryResponse(
    UUID id,
    String name,
    UUID parentId,
    String parentName,
    boolean system,
    String plaidCategoryId,
    Instant createdAt
) {}
```

### Pattern 3: Flyway Seed Data Migration
**What:** SQL INSERT statements for system categories in a versioned migration
**When to use:** Initial data that must exist for the app to function
**Example:**
```sql
-- V011__seed_plaid_categories.sql
-- Parent categories (is_system = TRUE, parent_id = NULL)
INSERT INTO categories (id, name, parent_id, plaid_category_id, is_system, created_at)
VALUES ('...uuid...', 'Alimentation & Restauration', NULL, 'FOOD_AND_DRINK', TRUE, NOW());

-- Child categories
INSERT INTO categories (id, name, parent_id, plaid_category_id, is_system, created_at)
VALUES ('...uuid...', 'Courses', '...parent-uuid...', 'FOOD_AND_DRINK_GROCERIES', TRUE, NOW());
```

### Pattern 4: PrimeNG TreeSelect with TreeNode
**What:** Hierarchical dropdown using PrimeNG's TreeNode interface
**When to use:** Category parent selector (shared component)
**Example:**
```typescript
// TreeNode structure for p-treeselect
interface TreeNode {
  label: string;
  data: string;        // category UUID
  children?: TreeNode[];
  selectable?: boolean;
}

// Transform flat categories to TreeNode hierarchy
function toTreeNodes(categories: CategoryResponse[]): TreeNode[] {
  const roots = categories.filter(c => !c.parentId);
  return roots.map(root => ({
    label: root.name,
    data: root.id,
    children: categories
      .filter(c => c.parentId === root.id)
      .map(child => ({ label: child.name, data: child.id }))
  }));
}
```

### Pattern 5: Angular Signal-based State (same as Phase 3)
**What:** Service with writable signal, readonly exposed to components
**Example:**
```typescript
@Injectable({ providedIn: 'root' })
export class CategoryService {
  private readonly http = inject(HttpClient);
  private categoriesSignal = signal<CategoryResponse[]>([]);
  readonly categories = this.categoriesSignal.asReadonly();

  loadCategories(): Observable<CategoryResponse[]> {
    return this.http.get<CategoryResponse[]>('/api/categories')
      .pipe(tap(cats => this.categoriesSignal.set(cats)));
  }
}
```

### Anti-Patterns to Avoid
- **Recursive depth queries:** With max depth 2, use simple `findByParentIsNull()` and `findByParent()` -- never recursive CTEs or @OneToMany eager loading
- **N+1 on parent name:** Return `parentName` in the DTO from a JOIN query, not via lazy loading in a loop
- **Mixing transaction concerns in category controller:** The `PATCH /api/transactions/{id}/category` belongs in a minimal `TransactionController`, not in `CategoryController`

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Hierarchical dropdown | Custom tree rendering | PrimeNG `p-treeselect` | Built-in keyboard nav, filter, a11y, TreeNode API |
| Category type badges | Custom styled spans | PrimeNG `p-tag` with severity | Consistent theming with Aura |
| Delete confirmation | Custom modal | PrimeNG `p-confirmdialog` | Focus trap, a11y, consistent UX |
| Flyway seed UUIDs | `gen_random_uuid()` | Hardcoded deterministic UUIDs | Reproducible across environments, testable FK references |

**Key insight:** PrimeNG's `TreeSelectModule` handles the entire hierarchical selection UX including filtering, keyboard navigation, and ARIA roles. The `TreeNode` interface maps naturally to a 2-level category hierarchy.

## Common Pitfalls

### Pitfall 1: LazyInitializationException on Category.parent
**What goes wrong:** Accessing `category.getParent().getName()` outside a transaction throws LazyInitializationException
**Why it happens:** `parent` is `FetchType.LAZY` (correct), but DTO mapping happens after the session closes
**How to avoid:** Use a JPQL query with JOIN FETCH or project parent name directly: `SELECT c, p.name FROM Category c LEFT JOIN c.parent p`
**Warning signs:** NullPointerException or LazyInitializationException in service layer

### Pitfall 2: Circular Parent Assignment
**What goes wrong:** A category is set as its own parent, or a child is set as parent of its parent
**Why it happens:** No validation on parentId
**How to avoid:** Validate in service: (1) parentId != id, (2) parent must be a root category (parentId is null) -- enforces max depth 2
**Warning signs:** Infinite loops in tree rendering

### Pitfall 3: Deleting Category with Transaction References
**What goes wrong:** FK violation on `transactions.category_id` when deleting a used category
**Why it happens:** No check before delete
**How to avoid:** Query `transactionRepository.existsByCategoryId(id)` before delete. Also check child categories: cannot delete a parent with children. Return 409 Conflict with descriptive message.
**Warning signs:** 500 Internal Server Error on delete

### Pitfall 4: TreeSelect Node Selection Returns TreeNode, Not UUID
**What goes wrong:** `p-treeselect` `ngModel` binds to a `TreeNode` object, not a plain string UUID
**Why it happens:** PrimeNG TreeSelect model is `TreeNode | TreeNode[]`, not the `data` property
**How to avoid:** Extract the UUID from `selectedNode.data` on selection change, or use `(onNodeSelect)` event to emit the `node.data` value
**Warning signs:** Sending `[object Object]` to the API instead of a UUID string

### Pitfall 5: Seed Migration UUID Consistency
**What goes wrong:** Using `gen_random_uuid()` in seed migration means parent UUIDs are unknown for child INSERT statements
**Why it happens:** UUIDs generated at runtime cannot be referenced in subsequent INSERT statements
**How to avoid:** Use hardcoded deterministic UUIDs in the migration file. Generate them once and hardcode them.
**Warning signs:** FK violation errors during migration

### Pitfall 6: Depth Constraint Not Enforced
**What goes wrong:** User creates a sub-sub-category (depth 3+) by selecting a child as parent
**Why it happens:** No depth validation
**How to avoid:** In the parent selector TreeSelect, only show root-level categories as selectable (filter out children). Additionally validate in backend: reject if `parentId` refers to a category that already has a parent.
**Warning signs:** UI breaks with unexpected nesting depth

## Code Examples

### Flyway V010: Add is_system Column
```sql
-- V010__add_is_system_to_categories.sql
ALTER TABLE categories ADD COLUMN is_system BOOLEAN NOT NULL DEFAULT FALSE;
```

### Flyway V011: Seed Curated Plaid Categories (excerpt)
```sql
-- V011__seed_plaid_categories.sql
-- Curated French household categories mapped to Plaid PFCv2 taxonomy
-- Using deterministic UUIDs for reproducibility

-- ROOT: Alimentation & Restauration (maps to FOOD_AND_DRINK)
INSERT INTO categories (id, name, parent_id, plaid_category_id, is_system, created_at)
VALUES ('a0000000-0000-0000-0000-000000000001', 'Alimentation & Restauration', NULL, 'FOOD_AND_DRINK', TRUE, NOW());

INSERT INTO categories (id, name, parent_id, plaid_category_id, is_system, created_at)
VALUES ('a0000000-0000-0000-0000-000000000002', 'Courses', 'a0000000-0000-0000-0000-000000000001', 'FOOD_AND_DRINK_GROCERIES', TRUE, NOW());

INSERT INTO categories (id, name, parent_id, plaid_category_id, is_system, created_at)
VALUES ('a0000000-0000-0000-0000-000000000003', 'Restaurant', 'a0000000-0000-0000-0000-000000000001', 'FOOD_AND_DRINK_RESTAURANT', TRUE, NOW());
```

### Plaid PFCv2 to French Household Mapping (recommended curated set)
```
Plaid PRIMARY              | French Label               | Subcategories
FOOD_AND_DRINK             | Alimentation & Restauration| Courses, Restaurant, Cafe
TRANSPORTATION             | Transport                  | Carburant, Transports en commun, Parking
RENT_AND_UTILITIES         | Logement & Charges         | Loyer, Electricite & Gaz, Internet & Telephone, Eau
MEDICAL                    | Sante                      | Pharmacie, Medecin, Dentiste
ENTERTAINMENT              | Loisirs & Culture          | Sorties, Streaming, Sport
GENERAL_MERCHANDISE        | Achats & Shopping          | Vetements, Electronique, Divers
GENERAL_SERVICES           | Services                   | Assurance, Education, Garde d'enfants
LOAN_PAYMENTS              | Remboursements             | Credit immobilier, Credit conso
INCOME                     | Revenus                    | Salaire, Interets, Remboursement impots
TRANSFER_IN / TRANSFER_OUT | Virements                  | Epargne, Virement compte
BANK_FEES                  | Frais bancaires            | (no subcategories needed)
GOVERNMENT_AND_NON_PROFIT  | Impots & Dons              | Impots, Dons
PERSONAL_CARE              | Soins personnels           | Coiffeur & Beaute, Salle de sport
TRAVEL                     | Voyages                    | Hebergement, Vols, Location voiture
```

### CategoryRepository Derived Queries
```java
public interface CategoryRepository extends JpaRepository<Category, UUID> {
    List<Category> findByParentIsNullOrderByNameAsc();  // root categories
    List<Category> findByParentIdOrderByNameAsc(UUID parentId);  // children of a parent
    List<Category> findAllByOrderByNameAsc();  // all categories sorted
    boolean existsByNameAndParentId(String name, UUID parentId);  // duplicate check
}
```

### PATCH Transaction Category Endpoint
```java
// In TransactionController (minimal -- only this endpoint in Phase 4)
@PatchMapping("/api/transactions/{id}/category")
public ResponseEntity<Void> updateCategory(
    @PathVariable UUID id,
    @Valid @RequestBody UpdateTransactionCategoryRequest request) {
  transactionService.updateCategory(id, request.categoryId());
  return ResponseEntity.noContent().build();
}

public record UpdateTransactionCategoryRequest(UUID categoryId) {}
```

### Frontend CategorySelector Shared Component
```typescript
// shared/category-selector.ts
@Component({
  selector: 'app-category-selector',
  imports: [TreeSelectModule, FormsModule, FloatLabelModule],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <p-treeselect
      [options]="options()"
      [(ngModel)]="selectedNode"
      [filter]="true"
      [showClear]="true"
      selectionMode="single"
      [placeholder]="placeholder()"
      appendTo="body"
      (onNodeSelect)="onSelect($event)"
      (onClear)="onClear()"
      styleClass="w-full"
    />
  `
})
export class CategorySelector {
  options = input.required<TreeNode[]>();
  placeholder = input('Categorie parente (optionnel)');
  selectedCategoryId = input<string | null>(null);
  categorySelected = output<string | null>();

  protected selectedNode: TreeNode | null = null;
  // Sync selectedNode from input when editing
}
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Plaid legacy categories (hierarchical array) | PFCv2 (primary + detailed strings) | Dec 2025 | `plaid_category_id` uses PFCv2 `detailed` string as unique identifier |
| PrimeNG TreeSelect overlay panel | PrimeNG 21 standalone TreeSelectModule | 2025 | Import `TreeSelectModule` directly, no NgModule needed |

**Deprecated/outdated:**
- Plaid legacy category hierarchy (3-level array of strings) replaced by PFCv2 (primary/detailed string pair) since Dec 2025

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework (backend) | JUnit 5 + Spring Boot Test + Testcontainers 2.x |
| Framework (frontend) | Angular 21 built-in test (`@angular/build:unit-test`) |
| Backend quick run | `./mvnw test -pl backend -Dtest=CategoryControllerTest` |
| Frontend quick run | `pnpm test` |
| Full suite | `./mvnw verify && pnpm test && pnpm lint` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| CATG-01 | System categories seeded and available via GET /api/categories | integration | `./mvnw test -pl backend -Dtest=CategoryControllerTest#list_returns_seeded_system_categories` | Wave 0 |
| CATG-02 | PATCH /api/transactions/{id}/category updates category | integration | `./mvnw test -pl backend -Dtest=TransactionControllerTest#update_category_returns_204` | Wave 0 |
| CATG-03 | POST /api/categories creates custom category | integration | `./mvnw test -pl backend -Dtest=CategoryControllerTest#create_custom_category_returns_201` | Wave 0 |
| CATG-03 | DELETE blocked when category used by transactions (409) | integration | `./mvnw test -pl backend -Dtest=CategoryControllerTest#delete_used_category_returns_409` | Wave 0 |
| CATG-04 | Categories returned with parent hierarchy | integration | `./mvnw test -pl backend -Dtest=CategoryControllerTest#list_returns_categories_with_parent_info` | Wave 0 |
| CATG-04 | CategorySelector displays tree hierarchy | unit (frontend) | `pnpm test -- --testPathPattern category-selector` | Wave 0 |

### Sampling Rate
- **Per task commit:** `./mvnw test -pl backend && pnpm test`
- **Per wave merge:** `./mvnw verify && pnpm test && pnpm lint`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `backend/src/test/java/com/prosperity/category/CategoryControllerTest.java` -- covers CATG-01, CATG-03, CATG-04
- [ ] `backend/src/test/java/com/prosperity/transaction/TransactionControllerTest.java` -- covers CATG-02
- [ ] `frontend/src/app/categories/category.service.spec.ts` -- covers service HTTP calls
- [ ] `frontend/src/app/categories/categories.spec.ts` -- covers list page
- [ ] `frontend/src/app/shared/category-selector.spec.ts` -- covers CATG-04 tree hierarchy

## Open Questions

1. **Exact curated category count**
   - What we know: D-02 says ~20-30 categories. The Plaid PFCv2 taxonomy has 17 primary categories with ~90 detailed categories. The CONTEXT.md suggests a French-localized subset.
   - What's unclear: Exact number of subcategories per parent -- the curated set needs to balance coverage with simplicity.
   - Recommendation: Start with ~12 root categories and ~20 subcategories (total ~32) covering the most common French household expenses. This is a planner decision -- the migration SQL will enumerate them.

2. **Transaction access control on PATCH category**
   - What we know: Phase 3 enforces access control on accounts. Transactions belong to accounts.
   - What's unclear: Should `PATCH /api/transactions/{id}/category` verify the user has WRITE access to the transaction's account?
   - Recommendation: Yes -- check that the authenticated user has at least WRITE access to the transaction's bank account before allowing category change. This prevents unauthorized category modifications.

## Sources

### Primary (HIGH confidence)
- Existing codebase: `Category.java`, `CategoryRepository.java`, `V004__create_categories.sql`, `Transaction.java` -- direct code inspection
- Existing codebase: Phase 3 patterns in `account/` package (Controller, Service, DTOs, tests) -- verified patterns
- [Plaid PFCv2 taxonomy CSV](https://plaid.com/documents/transactions-personal-finance-category-taxonomy.csv) -- complete category hierarchy fetched and analyzed
- [Plaid Transactions API docs](https://plaid.com/docs/api/products/transactions/) -- `personal_finance_category.detailed` as unique identifier format
- [PrimeNG TreeSelect documentation](https://primeng.org/treeselect) -- component API, TreeNode interface

### Secondary (MEDIUM confidence)
- [Plaid PFCv2 announcement](https://plaid.com/blog/ai-enhanced-transaction-categorization/) -- Dec 2025 release, migration details
- PrimeNG 21.1.4 installed in project -- verified `TreeSelectModule` availability

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- no new dependencies, all established in Phase 1-3
- Architecture: HIGH -- direct replication of Phase 3 patterns with minor additions
- Pitfalls: HIGH -- common JPA/Angular patterns, verified against codebase
- Plaid taxonomy mapping: MEDIUM -- curated subset is a design decision, not a technical constraint

**Research date:** 2026-04-05
**Valid until:** 2026-05-05 (stable domain, no fast-moving dependencies)
