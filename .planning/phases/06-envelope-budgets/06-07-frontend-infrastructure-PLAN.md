---
phase: 06-envelope-budgets
plan: 07
type: execute
wave: 3
depends_on:
  - 06-05-controllers-PLAN.md
files_modified:
  - frontend/src/app/envelopes/envelope.types.ts
  - frontend/src/app/envelopes/envelope.service.ts
  - frontend/src/app/shared/category-selector.ts
  - frontend/src/app/shared/category-selector.spec.ts
  - frontend/src/app/layout/sidebar.ts
  - frontend/src/app/layout/sidebar.spec.ts
  - frontend/src/app/app.routes.ts
autonomous: true
requirements:
  - ENVL-01
  - ENVL-02
  - ENVL-03
  - ENVL-06
  - ENVL-07
must_haves:
  truths:
    - "envelope.types.ts declares EnvelopeStatus, EnvelopeScope, RolloverPolicy, EnvelopeResponse, EnvelopeAllocationResponse, EnvelopeHistoryEntry, EnvelopeCategoryRef, CreateEnvelopeRequest, UpdateEnvelopeRequest, EnvelopeAllocationRequest matching backend record shapes verbatim"
    - "EnvelopeService (Angular) exposes signal-based loadEnvelopes, loadEnvelopesForAccount, getEnvelope, createEnvelope, updateEnvelope, deleteEnvelope, getHistory, listAllocations, createAllocation, updateAllocation, deleteAllocation"
    - "CategorySelector accepts selectionMode='single'|'checkbox' input; checkbox mode emits string[] via categoriesSelected output; single-mode existing behaviour preserved"
    - "Sidebar exposes Enveloppes link with pi-wallet icon (or pi-chart-pie if planner judges visual collision), routerLinkActive applied"
    - "app.routes.ts registers /envelopes (lazy) and /envelopes/:id (lazy) inside the authenticated layout children"
  artifacts:
    - path: "frontend/src/app/envelopes/envelope.types.ts"
      provides: "Frontend mirror of backend DTO records"
      contains: "interface EnvelopeResponse"
    - path: "frontend/src/app/envelopes/envelope.service.ts"
      provides: "HttpClient wrapper for envelope endpoints"
      contains: "@Injectable"
    - path: "frontend/src/app/shared/category-selector.ts"
      provides: "Extended single + checkbox tree-select"
      contains: "selectionMode"
    - path: "frontend/src/app/layout/sidebar.ts"
      provides: "Enveloppes nav entry"
      contains: "/envelopes"
    - path: "frontend/src/app/app.routes.ts"
      provides: "Lazy routes for envelopes pages"
      contains: "envelopes/envelopes"
  key_links:
    - from: "EnvelopeService"
      to: "/api/envelopes"
      via: "HttpClient.get/post/put/delete"
      pattern: "/api/envelopes"
    - from: "Sidebar"
      to: "/envelopes route"
      via: "routerLink=\"/envelopes\""
      pattern: "routerLink=\"/envelopes\""
    - from: "app.routes.ts"
      to: "EnvelopesPage + EnvelopeDetailsPage components"
      via: "loadComponent dynamic import"
      pattern: "loadComponent.*envelopes"
---

<objective>
Build the cross-feature scaffolding the frontend pages need before they can be implemented in Plan 08:
- TypeScript types mirroring the backend DTOs (single source of truth on the wire format)
- The HttpClient-based EnvelopeService (signal-aware)
- The extended CategorySelector that supports `selectionMode='checkbox'` (D-21, RESEARCH §Pattern 5)
- Sidebar Enveloppes link (D-15, UI-SPEC §Sidebar Entry)
- Lazy route registration (UI-SPEC §Routes)

Purpose: Plan 08 (the page components) consumes all of these. By isolating them in this plan we keep both plans reviewable in one sitting (project preference: atomic decoupling). Plan 07 also extends an existing shared component (CategorySelector) — a cross-cutting concern that benefits from being its own commit.

Output: 5 new/extended frontend files + 2 spec updates. All tests pass.
</objective>

<execution_context>
@/home/negus/dev/prosperity/.claude/get-shit-done/workflows/execute-plan.md
@/home/negus/dev/prosperity/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT.md
@.planning/ROADMAP.md
@.planning/phases/06-envelope-budgets/06-CONTEXT.md
@.planning/phases/06-envelope-budgets/06-RESEARCH.md
@.planning/phases/06-envelope-budgets/06-UI-SPEC.md

@frontend/src/app/transactions/transaction.types.ts
@frontend/src/app/transactions/transaction.service.ts
@frontend/src/app/shared/category-selector.ts
@frontend/src/app/shared/category-selector.spec.ts
@frontend/src/app/layout/sidebar.ts
@frontend/src/app/layout/sidebar.spec.ts
@frontend/src/app/app.routes.ts

<interfaces>
Backend DTOs (Plan 02) — exact shapes to mirror:
```
EnvelopeResponse(UUID id, UUID bankAccountId, String bankAccountName, String name,
    EnvelopeScope scope, UUID ownerId, List<EnvelopeCategoryRef> categories,
    RolloverPolicy rolloverPolicy, BigDecimal defaultBudget, BigDecimal effectiveBudget,
    BigDecimal consumed, BigDecimal available, BigDecimal ratio, EnvelopeStatus status,
    boolean hasMonthlyOverride, boolean archived, Instant createdAt)

EnvelopeAllocationResponse(UUID id, UUID envelopeId, YearMonth month, BigDecimal allocatedAmount, Instant createdAt)

EnvelopeHistoryEntry(YearMonth month, BigDecimal effectiveBudget, BigDecimal consumed,
    BigDecimal available, BigDecimal ratio, EnvelopeStatus status)

CreateEnvelopeRequest(String name, Set<UUID> categoryIds, BigDecimal budget, RolloverPolicy rolloverPolicy)
UpdateEnvelopeRequest(String name, Set<UUID> categoryIds, BigDecimal budget, RolloverPolicy rolloverPolicy)  // all nullable on the wire
EnvelopeAllocationRequest(YearMonth month, BigDecimal allocatedAmount)
```

JSON wire formats:
- BigDecimal -> JSON number (e.g. 100.00 — Jackson default)
- UUID -> string
- Instant -> ISO 8601 string
- YearMonth -> "yyyy-MM" string
- enums -> uppercase string ("PERSONAL", "SHARED", "RESET", "CARRY_OVER", "GREEN", "YELLOW", "RED")

REST routes (from Plan 05):
- GET /api/envelopes?accountId=X&includeArchived=true
- GET /api/accounts/{accountId}/envelopes?includeArchived=true
- POST /api/accounts/{accountId}/envelopes
- GET /api/envelopes/{id}
- PUT /api/envelopes/{id}
- DELETE /api/envelopes/{id}
- GET /api/envelopes/{id}/history?month=2026-04
- POST /api/envelopes/{id}/allocations
- GET /api/envelopes/{id}/allocations
- PUT /api/envelopes/allocations/{allocationId}
- DELETE /api/envelopes/allocations/{allocationId}

Existing CategorySelector (frontend/src/app/shared/category-selector.ts) — uses `p-treeselect` with `selectionMode="single"`. Has signals: options (input.required), placeholder (input), categorySelected (output), selectedNode (signal). Used by transactions filter.

Existing sidebar (frontend/src/app/layout/sidebar.ts) — has Comptes (with sub-list), Categories. Pattern: `<a routerLink routerLinkActive class>...`.

Existing app.routes.ts — has lazy children inside the authenticated layout: dashboard, accounts, categories, accounts/:accountId/transactions.
</interfaces>
</context>

<tasks>

<task type="auto" tdd="false">
  <name>Task 1: envelope.types.ts (TS interfaces matching backend records)</name>
  <files>frontend/src/app/envelopes/envelope.types.ts</files>
  <read_first>
    - frontend/src/app/transactions/transaction.types.ts (style reference for BigDecimal->number / Instant->string mapping)
    - .planning/phases/06-envelope-budgets/06-02-dtos-and-exceptions-PLAN.md (backend DTO definitions)
  </read_first>
  <action>
Create `frontend/src/app/envelopes/envelope.types.ts` with the exact contents below.

```typescript
export type EnvelopeStatus = 'GREEN' | 'YELLOW' | 'RED';
export type EnvelopeScope = 'PERSONAL' | 'SHARED';
export type RolloverPolicy = 'RESET' | 'CARRY_OVER';

export interface EnvelopeCategoryRef {
  id: string; // UUID
  name: string;
}

export interface EnvelopeResponse {
  id: string;
  bankAccountId: string;
  bankAccountName: string;
  name: string;
  scope: EnvelopeScope;
  ownerId: string | null;
  categories: EnvelopeCategoryRef[];
  rolloverPolicy: RolloverPolicy;
  defaultBudget: number;
  effectiveBudget: number;
  consumed: number;
  available: number;
  ratio: number;
  status: EnvelopeStatus;
  hasMonthlyOverride: boolean;
  archived: boolean;
  createdAt: string; // ISO 8601 instant
}

export interface EnvelopeAllocationResponse {
  id: string;
  envelopeId: string;
  month: string; // "yyyy-MM"
  allocatedAmount: number;
  createdAt: string;
}

export interface EnvelopeHistoryEntry {
  month: string; // "yyyy-MM"
  effectiveBudget: number;
  consumed: number;
  available: number;
  ratio: number;
  status: EnvelopeStatus;
}

export interface CreateEnvelopeRequest {
  name: string;
  categoryIds: string[];
  budget: number;
  rolloverPolicy: RolloverPolicy;
}

export interface UpdateEnvelopeRequest {
  name?: string | null;
  categoryIds?: string[] | null;
  budget?: number | null;
  rolloverPolicy?: RolloverPolicy | null;
}

export interface EnvelopeAllocationRequest {
  month: string; // "yyyy-MM"
  allocatedAmount: number;
}

export interface EnvelopeListFilters {
  accountId?: string | null;
  includeArchived?: boolean;
}
```

Notes:
- Number for monetary fields (Jackson serialises BigDecimal as JSON number) — match Phase 5 transaction.types.ts.
- Month strings are "yyyy-MM" (matches `@DateTimeFormat(pattern = "yyyy-MM")` on the backend).
- Categories are an array (preserves backend order).
- ownerId is nullable for SHARED envelopes.
  </action>
  <verify>
    <automated>cd /home/negus/dev/prosperity/frontend && pnpm exec tsc --noEmit -p tsconfig.app.json 2>&1 | tail -10</automated>
  </verify>
  <acceptance_criteria>
    - File `frontend/src/app/envelopes/envelope.types.ts` exists
    - `grep -c "export type EnvelopeStatus" frontend/src/app/envelopes/envelope.types.ts` returns 1
    - `grep -c "export type EnvelopeScope" frontend/src/app/envelopes/envelope.types.ts` returns 1
    - `grep -c "export type RolloverPolicy" frontend/src/app/envelopes/envelope.types.ts` returns 1
    - `grep -c "export interface EnvelopeResponse" frontend/src/app/envelopes/envelope.types.ts` returns 1
    - `grep -c "export interface EnvelopeAllocationResponse" frontend/src/app/envelopes/envelope.types.ts` returns 1
    - `grep -c "export interface EnvelopeHistoryEntry" frontend/src/app/envelopes/envelope.types.ts` returns 1
    - `grep -c "export interface CreateEnvelopeRequest" frontend/src/app/envelopes/envelope.types.ts` returns 1
    - `grep -c "export interface UpdateEnvelopeRequest" frontend/src/app/envelopes/envelope.types.ts` returns 1
    - `grep -c "export interface EnvelopeAllocationRequest" frontend/src/app/envelopes/envelope.types.ts` returns 1
    - `grep -c "GREEN" frontend/src/app/envelopes/envelope.types.ts` returns 1
    - `grep -c "YELLOW" frontend/src/app/envelopes/envelope.types.ts` returns 1
    - `grep -c "RED" frontend/src/app/envelopes/envelope.types.ts` returns 1
    - `pnpm exec tsc --noEmit -p tsconfig.app.json` exits 0 (no TypeScript errors)
  </acceptance_criteria>
  <done>envelope.types.ts type-checks cleanly and exposes every interface/type the rest of the frontend needs.</done>
</task>

<task type="auto" tdd="false">
  <name>Task 2: envelope.service.ts (HttpClient + signals)</name>
  <files>frontend/src/app/envelopes/envelope.service.ts</files>
  <read_first>
    - frontend/src/app/envelopes/envelope.types.ts (Task 1 output)
    - frontend/src/app/transactions/transaction.service.ts (canonical HttpClient + HttpParams pattern; copy structure verbatim)
    - frontend/src/app/accounts/account.service.ts (signal pattern reference if it diverges from transactions)
  </read_first>
  <action>
Create `frontend/src/app/envelopes/envelope.service.ts`:

```typescript
import { Injectable, inject, signal } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable, tap } from 'rxjs';
import {
  EnvelopeResponse,
  EnvelopeAllocationResponse,
  EnvelopeHistoryEntry,
  CreateEnvelopeRequest,
  UpdateEnvelopeRequest,
  EnvelopeAllocationRequest,
  EnvelopeListFilters,
} from './envelope.types';

@Injectable({ providedIn: 'root' })
export class EnvelopeService {
  private readonly http = inject(HttpClient);

  /** In-memory cache used by the list page; pages may also read directly from observables. */
  private readonly _envelopes = signal<EnvelopeResponse[]>([]);
  readonly envelopes = this._envelopes.asReadonly();

  // ----- Envelopes -----

  loadEnvelopes(filters: EnvelopeListFilters = {}): Observable<EnvelopeResponse[]> {
    let params = new HttpParams();
    if (filters.accountId) params = params.set('accountId', filters.accountId);
    if (filters.includeArchived) params = params.set('includeArchived', 'true');
    return this.http
      .get<EnvelopeResponse[]>('/api/envelopes', { params })
      .pipe(tap((list) => this._envelopes.set(list)));
  }

  loadEnvelopesForAccount(
    accountId: string,
    includeArchived = false,
  ): Observable<EnvelopeResponse[]> {
    let params = new HttpParams();
    if (includeArchived) params = params.set('includeArchived', 'true');
    return this.http
      .get<EnvelopeResponse[]>(`/api/accounts/${accountId}/envelopes`, { params })
      .pipe(tap((list) => this._envelopes.set(list)));
  }

  getEnvelope(id: string): Observable<EnvelopeResponse> {
    return this.http.get<EnvelopeResponse>(`/api/envelopes/${id}`);
  }

  createEnvelope(
    accountId: string,
    request: CreateEnvelopeRequest,
  ): Observable<EnvelopeResponse> {
    return this.http.post<EnvelopeResponse>(
      `/api/accounts/${accountId}/envelopes`,
      request,
    );
  }

  updateEnvelope(
    id: string,
    request: UpdateEnvelopeRequest,
  ): Observable<EnvelopeResponse> {
    return this.http.put<EnvelopeResponse>(`/api/envelopes/${id}`, request);
  }

  deleteEnvelope(id: string): Observable<void> {
    return this.http.delete<void>(`/api/envelopes/${id}`);
  }

  /** History returns 12 months ending at {@code month} (defaults to current month server-side). */
  getHistory(id: string, month?: string): Observable<EnvelopeHistoryEntry[]> {
    let params = new HttpParams();
    if (month) params = params.set('month', month);
    return this.http.get<EnvelopeHistoryEntry[]>(`/api/envelopes/${id}/history`, {
      params,
    });
  }

  // ----- Allocations -----

  listAllocations(envelopeId: string): Observable<EnvelopeAllocationResponse[]> {
    return this.http.get<EnvelopeAllocationResponse[]>(
      `/api/envelopes/${envelopeId}/allocations`,
    );
  }

  createAllocation(
    envelopeId: string,
    request: EnvelopeAllocationRequest,
  ): Observable<EnvelopeAllocationResponse> {
    return this.http.post<EnvelopeAllocationResponse>(
      `/api/envelopes/${envelopeId}/allocations`,
      request,
    );
  }

  updateAllocation(
    allocationId: string,
    request: EnvelopeAllocationRequest,
  ): Observable<EnvelopeAllocationResponse> {
    return this.http.put<EnvelopeAllocationResponse>(
      `/api/envelopes/allocations/${allocationId}`,
      request,
    );
  }

  deleteAllocation(allocationId: string): Observable<void> {
    return this.http.delete<void>(`/api/envelopes/allocations/${allocationId}`);
  }
}
```
  </action>
  <verify>
    <automated>cd /home/negus/dev/prosperity/frontend && pnpm exec tsc --noEmit -p tsconfig.app.json 2>&1 | tail -10</automated>
  </verify>
  <acceptance_criteria>
    - File `frontend/src/app/envelopes/envelope.service.ts` exists
    - `grep -c "@Injectable" frontend/src/app/envelopes/envelope.service.ts` returns 1
    - `grep -c "loadEnvelopes" frontend/src/app/envelopes/envelope.service.ts` returns at least 2 (declaration + readonly signal usage)
    - `grep -c "loadEnvelopesForAccount" frontend/src/app/envelopes/envelope.service.ts` returns 1
    - `grep -c "createEnvelope" frontend/src/app/envelopes/envelope.service.ts` returns 1
    - `grep -c "updateEnvelope" frontend/src/app/envelopes/envelope.service.ts` returns 1
    - `grep -c "deleteEnvelope" frontend/src/app/envelopes/envelope.service.ts` returns 1
    - `grep -c "getHistory" frontend/src/app/envelopes/envelope.service.ts` returns 1
    - `grep -c "listAllocations" frontend/src/app/envelopes/envelope.service.ts` returns 1
    - `grep -c "createAllocation" frontend/src/app/envelopes/envelope.service.ts` returns 1
    - `grep -c "updateAllocation" frontend/src/app/envelopes/envelope.service.ts` returns 1
    - `grep -c "deleteAllocation" frontend/src/app/envelopes/envelope.service.ts` returns 1
    - `grep -c "/api/envelopes" frontend/src/app/envelopes/envelope.service.ts` returns at least 6
    - `grep -c "/api/accounts/" frontend/src/app/envelopes/envelope.service.ts` returns at least 2
    - `pnpm exec tsc --noEmit -p tsconfig.app.json` exits 0
  </acceptance_criteria>
  <done>EnvelopeService compiles, exposes 11 public methods covering all 11 backend routes; envelopes signal is readonly outside the service.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 3: Extend CategorySelector with selectionMode='checkbox' (D-21, RESEARCH §Pattern 5)</name>
  <files>frontend/src/app/shared/category-selector.ts, frontend/src/app/shared/category-selector.spec.ts</files>
  <read_first>
    - frontend/src/app/shared/category-selector.ts (current single-mode implementation)
    - frontend/src/app/shared/category-selector.spec.ts (existing tests — DO NOT BREAK)
    - .planning/phases/06-envelope-budgets/06-UI-SPEC.md (Extended CategorySelector Contract section, lines 170-187)
  </read_first>
  <behavior>
    - Existing single-mode behaviour preserved: `selectionMode='single'` (default), `categorySelected` emits `string | null`
    - New checkbox mode: `selectionMode='checkbox'`, accepts `selectedIds = input<string[]>(...)` to programmatically pre-fill, emits `categoriesSelected = output<string[]>` whenever the user changes selection
    - In checkbox mode, p-treeSelect uses `selectionMode="checkbox"` and `display="chip"` with `showClear=true`
    - Placeholder customizable via existing `placeholder` input
    - Existing single-mode tests (category-selector.spec.ts) still pass
    - New tests cover: checkbox mode emits string[] on selection, single mode unchanged, two modes coexist via the same component instance type
  </behavior>
  <action>
**File 1: `frontend/src/app/shared/category-selector.ts`** — modify the existing component to add the new mode while preserving the old API. Replace the file contents:

```typescript
import {
  ChangeDetectionStrategy,
  Component,
  computed,
  effect,
  input,
  output,
  signal,
} from '@angular/core';
import { FormsModule } from '@angular/forms';
import { TreeSelectModule } from 'primeng/treeselect';
import { TreeNode } from 'primeng/api';

type SelectionMode = 'single' | 'checkbox';

@Component({
  selector: 'app-category-selector',
  imports: [TreeSelectModule, FormsModule],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    @if (selectionMode() === 'single') {
      <p-treeselect
        [options]="options()"
        [(ngModel)]="selectedNode"
        [filter]="true"
        [showClear]="true"
        selectionMode="single"
        [placeholder]="placeholder()"
        appendTo="body"
        (onNodeSelect)="onSingleSelect($event)"
        (onClear)="onSingleClear()"
        styleClass="w-full"
      />
    } @else {
      <p-treeselect
        [options]="options()"
        [(ngModel)]="selectedNodes"
        [filter]="true"
        [showClear]="true"
        selectionMode="checkbox"
        display="chip"
        [placeholder]="placeholder()"
        appendTo="body"
        [metaKeySelection]="false"
        (onNodeSelect)="onCheckboxChange()"
        (onNodeUnselect)="onCheckboxChange()"
        (onClear)="onCheckboxClear()"
        styleClass="w-full"
      />
    }
  `,
})
export class CategorySelector {
  options = input.required<TreeNode[]>();
  placeholder = input('Categorie parente (optionnel)');
  selectionMode = input<SelectionMode>('single');
  /** Pre-fill selection in checkbox mode (UUID list). Ignored in single mode. */
  selectedIds = input<string[]>([]);

  // Single-mode existing API (unchanged)
  categorySelected = output<string | null>();

  // Checkbox-mode new API
  categoriesSelected = output<string[]>();

  private readonly _selectedNode = signal<TreeNode | null>(null);
  private readonly _selectedNodes = signal<TreeNode[]>([]);

  constructor() {
    // When parent updates selectedIds + options, reflect into the internal multi-selection signal.
    effect(() => {
      if (this.selectionMode() !== 'checkbox') return;
      const ids = new Set(this.selectedIds());
      const flat = this.flatten(this.options());
      this._selectedNodes.set(flat.filter((n) => ids.has(n.data as string)));
    });
  }

  // Single-mode getter/setter for [(ngModel)]
  get selectedNode(): TreeNode | null {
    return this._selectedNode();
  }
  set selectedNode(value: TreeNode | null) {
    this._selectedNode.set(value);
  }

  // Checkbox-mode getter/setter for [(ngModel)]
  get selectedNodes(): TreeNode[] {
    return this._selectedNodes();
  }
  set selectedNodes(value: TreeNode[]) {
    this._selectedNodes.set(value ?? []);
  }

  onSingleSelect(event: { node: TreeNode }): void {
    this.categorySelected.emit(event.node.data as string);
  }

  onSingleClear(): void {
    this._selectedNode.set(null);
    this.categorySelected.emit(null);
  }

  onCheckboxChange(): void {
    const ids = this._selectedNodes().map((n) => n.data as string);
    this.categoriesSelected.emit(ids);
  }

  onCheckboxClear(): void {
    this._selectedNodes.set([]);
    this.categoriesSelected.emit([]);
  }

  /** Programmatically sets the single-mode selection (e.g. edit mode). Triggers change detection via signal. */
  setSelection(node: TreeNode | null): void {
    this._selectedNode.set(node);
  }

  private flatten(nodes: TreeNode[]): TreeNode[] {
    const out: TreeNode[] = [];
    const walk = (list: TreeNode[]) => {
      for (const n of list) {
        out.push(n);
        if (n.children?.length) walk(n.children);
      }
    };
    walk(nodes);
    return out;
  }
}
```

**File 2: `frontend/src/app/shared/category-selector.spec.ts`** — add new test cases preserving existing ones. Keep the existing test descriptions; append new `describe('checkbox mode')` block. The exact additions (Vitest, mirrors existing style):

After the existing tests, append:

```typescript
describe('CategorySelector checkbox mode', () => {
  it('emits empty array when no checkboxes selected and clear is pressed', async () => {
    // Arrange
    const fixture = TestBed.createComponent(CategorySelector);
    fixture.componentRef.setInput('options', sampleOptions());
    fixture.componentRef.setInput('selectionMode', 'checkbox');
    fixture.componentRef.setInput('selectedIds', []);
    fixture.detectChanges();
    const emitted: string[][] = [];
    fixture.componentInstance.categoriesSelected.subscribe((ids) => emitted.push(ids));

    // Act
    fixture.componentInstance.onCheckboxClear();

    // Assert
    expect(emitted).toEqual([[]]);
  });

  it('emits selected ids array when checkbox selection changes', () => {
    // Arrange
    const fixture = TestBed.createComponent(CategorySelector);
    const opts = sampleOptions();
    fixture.componentRef.setInput('options', opts);
    fixture.componentRef.setInput('selectionMode', 'checkbox');
    fixture.componentRef.setInput('selectedIds', []);
    fixture.detectChanges();
    const emitted: string[][] = [];
    fixture.componentInstance.categoriesSelected.subscribe((ids) => emitted.push(ids));
    // Simulate the [(ngModel)] write
    fixture.componentInstance.selectedNodes = [opts[0], opts[0].children![0]];

    // Act
    fixture.componentInstance.onCheckboxChange();

    // Assert
    expect(emitted).toEqual([[opts[0].data, opts[0].children![0].data]]);
  });

  it('preserves single-mode behaviour when selectionMode is omitted', () => {
    // Arrange
    const fixture = TestBed.createComponent(CategorySelector);
    fixture.componentRef.setInput('options', sampleOptions());
    fixture.detectChanges();
    const emitted: (string | null)[] = [];
    fixture.componentInstance.categorySelected.subscribe((id) => emitted.push(id));

    // Act
    fixture.componentInstance.onSingleSelect({ node: sampleOptions()[0] });

    // Assert
    expect(emitted).toEqual([sampleOptions()[0].data]);
  });
});

function sampleOptions() {
  return [
    {
      label: 'Alimentation',
      data: 'cat-root',
      children: [
        { label: 'Courses', data: 'cat-courses' },
        { label: 'Restaurant', data: 'cat-resto' },
      ],
    },
  ];
}
```

If the existing spec file has a different `sampleOptions` helper, REUSE it instead of duplicating; otherwise add the helper as shown.

If existing single-mode tests already cover what `preserves single-mode behaviour when selectionMode is omitted` would test, omit that one and rely on existing tests. The point: do NOT remove or weaken existing tests; only add coverage for the new mode.
  </action>
  <verify>
    <automated>cd /home/negus/dev/prosperity/frontend && pnpm test -- --run src/app/shared/category-selector.spec.ts 2>&1 | tail -20</automated>
  </verify>
  <acceptance_criteria>
    - `grep -c "selectionMode = input<SelectionMode>" frontend/src/app/shared/category-selector.ts` returns 1
    - `grep -c "selectedIds = input<string\\[\\]>" frontend/src/app/shared/category-selector.ts` returns 1
    - `grep -c "categoriesSelected = output<string\\[\\]>" frontend/src/app/shared/category-selector.ts` returns 1
    - `grep -c "categorySelected = output<string | null>" frontend/src/app/shared/category-selector.ts` returns 1 (single-mode preserved)
    - `grep -c "selectionMode=\"checkbox\"" frontend/src/app/shared/category-selector.ts` returns 1
    - `grep -c "selectionMode=\"single\"" frontend/src/app/shared/category-selector.ts` returns 1
    - `grep -c "display=\"chip\"" frontend/src/app/shared/category-selector.ts` returns 1
    - `grep -c "describe.*checkbox" frontend/src/app/shared/category-selector.spec.ts` returns at least 1
    - `pnpm test -- --run src/app/shared/category-selector.spec.ts` exits 0; vitest output shows existing tests still passing AND at least 2 new checkbox-mode tests passing
  </acceptance_criteria>
  <done>CategorySelector now supports both single and checkbox modes; existing tests still pass; at least 2 new tests cover checkbox emission behaviour.</done>
</task>

<task type="auto" tdd="false">
  <name>Task 4: Sidebar Enveloppes link + sidebar.spec assertion + app.routes.ts lazy routes</name>
  <files>frontend/src/app/layout/sidebar.ts, frontend/src/app/layout/sidebar.spec.ts, frontend/src/app/app.routes.ts</files>
  <read_first>
    - frontend/src/app/layout/sidebar.ts (current state — locate the Categories link block)
    - frontend/src/app/layout/sidebar.spec.ts (existing tests — verify pattern for asserting link presence)
    - frontend/src/app/app.routes.ts (current routes — locate the authenticated layout children block)
    - .planning/phases/06-envelope-budgets/06-UI-SPEC.md (Sidebar Entry section, lines 117-140 — exact markup contract)
  </read_first>
  <action>
**File 1: `frontend/src/app/layout/sidebar.ts`** — add the Enveloppes link AFTER the existing Categories link, BEFORE the closing `</nav>`. Insert exactly:

```html
        <a
          routerLink="/envelopes"
          routerLinkActive="bg-surface-100 text-primary font-semibold border-l-3 border-primary"
          class="flex items-center gap-3 px-3 py-2 rounded-md text-muted-color hover:bg-surface-50 transition-colors"
        >
          <i class="pi pi-wallet" aria-hidden="true"></i>
          <span>Enveloppes</span>
        </a>
```

Do NOT modify any existing link, ordering, or class. Do NOT add new component-level imports beyond what's already there (RouterLink + RouterLinkActive are already imported).

NOTE: `pi-wallet` is intentionally reused to keep visual consistency. UI-SPEC notes `pi-chart-pie` is an acceptable alternative if you judge collision with the Comptes link too strong; default to `pi-wallet` per UI-SPEC line 140.

**File 2: `frontend/src/app/layout/sidebar.spec.ts`** — add a single assertion: the rendered sidebar contains an `<a>` with `routerLink="/envelopes"` and visible text "Enveloppes". Append a new test like:

```typescript
it('renders the Enveloppes navigation link', () => {
  // Arrange
  const fixture = TestBed.createComponent(Sidebar);
  fixture.detectChanges();

  // Act
  const link = fixture.nativeElement.querySelector('a[routerLink="/envelopes"]');

  // Assert
  expect(link).not.toBeNull();
  expect(link.textContent).toContain('Enveloppes');
});
```

Do not break existing tests.

**File 3: `frontend/src/app/app.routes.ts`** — add two new lazy children INSIDE the authenticated layout `children:` array, AFTER the existing `accounts/:accountId/transactions` entry and BEFORE the empty-path redirect:

```typescript
      {
        path: 'envelopes',
        loadComponent: () =>
          import('./envelopes/envelopes').then((m) => m.EnvelopesPage),
      },
      {
        path: 'envelopes/:id',
        loadComponent: () =>
          import('./envelopes/envelope-details').then((m) => m.EnvelopeDetailsPage),
      },
```

The component class names `EnvelopesPage` and `EnvelopeDetailsPage` MUST match the exports in Plan 08. If Plan 08 changes the names, this file must be updated; the contract is locked here.
  </action>
  <verify>
    <automated>cd /home/negus/dev/prosperity/frontend && pnpm test -- --run src/app/layout/sidebar.spec.ts 2>&1 | tail -15 && pnpm exec tsc --noEmit -p tsconfig.app.json 2>&1 | tail -5</automated>
  </verify>
  <acceptance_criteria>
    - `grep -c "routerLink=\"/envelopes\"" frontend/src/app/layout/sidebar.ts` returns 1
    - `grep -c "Enveloppes" frontend/src/app/layout/sidebar.ts` returns 1
    - `grep -c "pi-wallet\\|pi-chart-pie" frontend/src/app/layout/sidebar.ts` returns at least 1 (existing or new — both icons are acceptable for new entry)
    - `grep -c "routerLink=\"/categories\"" frontend/src/app/layout/sidebar.ts` returns 1 (existing preserved)
    - `grep -c "routerLink=\"/accounts\"" frontend/src/app/layout/sidebar.ts` returns 1 (existing preserved)
    - `grep -c "renders the Enveloppes navigation link" frontend/src/app/layout/sidebar.spec.ts` returns 1
    - `grep -c "path: 'envelopes'" frontend/src/app/app.routes.ts` returns 1
    - `grep -c "path: 'envelopes/:id'" frontend/src/app/app.routes.ts` returns 1
    - `grep -c "envelopes/envelopes" frontend/src/app/app.routes.ts` returns 1
    - `grep -c "envelopes/envelope-details" frontend/src/app/app.routes.ts` returns 1
    - `grep -c "EnvelopesPage" frontend/src/app/app.routes.ts` returns 1
    - `grep -c "EnvelopeDetailsPage" frontend/src/app/app.routes.ts` returns 1
    - `pnpm test -- --run src/app/layout/sidebar.spec.ts` exits 0 with new test green and existing ones intact
    - `pnpm exec tsc --noEmit -p tsconfig.app.json` exits 0 (note: the loadComponent import targets files NOT YET created in Plan 08 — TypeScript may show "Cannot find module './envelopes/envelopes'" until Plan 08 lands. If so, suppress via TODO marker comments and re-run after Plan 08, OR create empty stub files `frontend/src/app/envelopes/envelopes.ts` exporting `export class EnvelopesPage {}` and same for envelope-details.ts to keep the build green between plans)
  </acceptance_criteria>
  <done>Sidebar shows Enveloppes link, sidebar test asserts its presence, routes are wired (with optional empty stub component classes if needed for type-check between plans).</done>
</task>

</tasks>

<verification>
- `pnpm exec tsc --noEmit -p tsconfig.app.json` exits 0 (after stub components are in place if Plan 08 hasn't landed yet).
- `pnpm test -- --run src/app/shared/category-selector.spec.ts` passes (existing single-mode tests + new checkbox tests).
- `pnpm test -- --run src/app/layout/sidebar.spec.ts` passes (existing tests + new Enveloppes link test).
- `pnpm lint -- --max-warnings 0` exits 0 (project lint policy).
</verification>

<success_criteria>
- envelope.types.ts exports the 9 named types/interfaces matching backend records.
- envelope.service.ts provides 11 methods covering all 11 backend routes.
- CategorySelector supports both modes; existing tests still green; new checkbox tests added.
- Sidebar exposes Enveloppes link with routerLinkActive styling.
- app.routes.ts registers both /envelopes and /envelopes/:id lazy routes.
- All frontend builds and unit tests pass.
</success_criteria>

<output>
After completion, create `.planning/phases/06-envelope-budgets/06-07-frontend-infrastructure-SUMMARY.md`.
</output>
