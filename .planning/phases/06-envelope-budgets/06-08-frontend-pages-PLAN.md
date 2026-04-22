---
phase: 06-envelope-budgets
plan: 08
type: execute
wave: 4
depends_on:
  - 06-07-frontend-infrastructure-PLAN.md
files_modified:
  - frontend/src/app/envelopes/envelopes.ts
  - frontend/src/app/envelopes/envelopes.spec.ts
  - frontend/src/app/envelopes/envelope-dialog.ts
  - frontend/src/app/envelopes/envelope-dialog.spec.ts
  - frontend/src/app/envelopes/envelope-details.ts
  - frontend/src/app/envelopes/envelope-details.spec.ts
  - frontend/src/app/envelopes/envelope-allocation-dialog.ts
  - frontend/src/app/envelopes/envelope-allocation-dialog.spec.ts
  - frontend/src/app/envelopes/envelope.service.spec.ts
  - .planning/phases/06-envelope-budgets/06-VALIDATION.md
autonomous: false
requirements:
  - ENVL-01
  - ENVL-02
  - ENVL-03
  - ENVL-04
  - ENVL-05
  - ENVL-06
  - ENVL-07
must_haves:
  truths:
    - "EnvelopesPage (/envelopes) renders a p-table of envelopes filtered by ?accountId, with status p-tag (severity success/warn/danger from EnvelopeStatus mapping) + p-progressbar (clamped at 100% display, ARIA describes real percentage)"
    - "Filter bar exposes Compte p-select (incl. 'Tous les comptes' option, value=null) and Afficher les archivees p-toggleswitch, both syncing with URL query params"
    - "Empty states cover: no envelopes (with create CTA), filtered-empty (with reset CTA), no accounts (orphan dependency redirect to /accounts)"
    - "Envelope dialog (create/edit) uses extended CategorySelector in checkbox mode, p-inputnumber EUR fr-FR, p-selectbutton for rollover, scope tag derived from selected account, save disabled when invalid (name blank OR no categories OR budget null/<0 OR no account)"
    - "Envelope dialog handles 403 -> 'Vous n''avez pas les droits...' message and 409 -> 'Une categorie selectionnee appartient deja a une autre enveloppe...' message verbatim per UI-SPEC Copywriting Contract"
    - "Envelope details page (/envelopes/:id) shows current month summary card (Budget effectif, Consomme, Restant) + 12-month history p-table with row navigation to /accounts/{id}/transactions"
    - "Envelope allocation dialog (Personnaliser ce mois) supports create + delete on existing overrides, defaults to current month"
    - "Sidebar entry from Plan 07 navigates to /envelopes on click"
    - "Frontend test suite covers: list page status badges, filter behaviour, dialog validation, multi-category emission, history table month rendering, service HttpClient interactions"
    - "Frontend specs use provideRouter([]) (Angular 21 standalone-router pattern), NOT the deprecated RouterTestingModule.withRoutes([])"
    - "06-VALIDATION.md nyquist_compliant flag flips to true at the end of Plan 08 (after the full envelope vitest suite runs green)"
  artifacts:
    - path: "frontend/src/app/envelopes/envelopes.ts"
      provides: "List page (/envelopes) with p-table, filter bar, dialogs"
      contains: "EnvelopesPage"
    - path: "frontend/src/app/envelopes/envelope-dialog.ts"
      provides: "Create/edit p-dialog with multi-select categories"
      contains: "EnvelopeDialog"
    - path: "frontend/src/app/envelopes/envelope-details.ts"
      provides: "Details page (/envelopes/:id) with summary + 12-month history"
      contains: "EnvelopeDetailsPage"
    - path: "frontend/src/app/envelopes/envelope-allocation-dialog.ts"
      provides: "Monthly override CRUD sub-dialog"
      contains: "EnvelopeAllocationDialog"
    - path: "frontend/src/app/envelopes/envelope.service.spec.ts"
      provides: "HttpClient signal service tests"
      contains: "provideHttpClientTesting"
  key_links:
    - from: "EnvelopesPage"
      to: "EnvelopeService"
      via: "constructor injection + loadEnvelopes call"
      pattern: "envelopeService"
    - from: "EnvelopesPage status column"
      to: "EnvelopeStatus enum"
      via: "statusSeverity() and statusLabel() helper functions"
      pattern: "(GREEN|YELLOW|RED)"
    - from: "EnvelopeDialog category multi-select"
      to: "Extended CategorySelector"
      via: "selectionMode=\"checkbox\""
      pattern: "selectionMode=\"checkbox\""
---

<objective>
Build the user-facing Phase 6 surface:
- `/envelopes` list page (Page 1 of UI-SPEC) with filter bar, status indicators, dialogs
- `/envelopes/:id` details page (Page 2 of UI-SPEC) with current-month summary + 12-month history
- Create/edit envelope dialog (Dialog 1 of UI-SPEC) with multi-category selection
- Monthly override allocation dialog (Dialog 2 of UI-SPEC)
- Vitest specs covering interaction-level tests for each component + service

This plan implements the UI-SPEC Copywriting Contract verbatim and applies the Status -> p-tag severity mapping owned by the server (D-13 single source of truth).

Purpose: Closes the Phase 6 deliverable. After this plan, all 7 ENVL requirements are user-testable.

Output: 4 component files + 4 spec files + 1 service spec + 06-VALIDATION.md `nyquist_compliant` flip, plus a checkpoint:human-verify gate so the user can confirm the UX/A11y aspects (color contrast, keyboard nav, French copy) before phase verification.
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
@.planning/phases/06-envelope-budgets/06-VALIDATION.md

@frontend/src/app/transactions/transactions.ts
@frontend/src/app/transactions/transaction-dialog.ts
@frontend/src/app/transactions/transactions.spec.ts
@frontend/src/app/transactions/transaction-dialog.spec.ts
@frontend/src/app/categories/categories.ts
@frontend/src/app/accounts/account-details.ts
@frontend/src/app/envelopes/envelope.types.ts
@frontend/src/app/envelopes/envelope.service.ts
@frontend/src/app/shared/category-selector.ts
@frontend/src/app/accounts/account.service.ts
@frontend/src/app/categories/category.service.ts

<revision_note>
**Iteration 1 revision (WARNING 2):** All references to `RouterTestingModule.withRoutes([])` replaced with `provideRouter([])` from `@angular/router` (Angular 21 standalone-router pattern; RouterTestingModule is deprecated). Affects Tasks 1 and 2 spec files. Also adds the `nyquist_compliant: true` frontmatter flip to 06-VALIDATION.md as the final acceptance step of Plan 08 — semantically correct because Wave 0 was scaffolding (delivered by Plan 03), nyquist compliance requires the test BODIES to be green, which only fully obtains once the frontend specs run green here.
</revision_note>

<interfaces>
EnvelopeService (Plan 07): loadEnvelopes(filters), loadEnvelopesForAccount(accountId, includeArchived), getEnvelope, createEnvelope, updateEnvelope, deleteEnvelope, getHistory, listAllocations, createAllocation, updateAllocation, deleteAllocation.

CategorySelector (Plan 07 extended): inputs `options: TreeNode[]`, `placeholder`, `selectionMode: 'single' | 'checkbox'`, `selectedIds: string[]`. Outputs `categorySelected: string|null` (single), `categoriesSelected: string[]` (checkbox).

AccountService (existing): provides `accounts` signal of AccountResponse[] (id, name, accountType, currentUserAccessLevel).

CategoryService (existing): provides categories as TreeNode[] for tree-select components (root with children).

Status mapping (helpers must implement):
- statusLabel(GREEN) -> "Sur la bonne voie"
- statusLabel(YELLOW) -> "Attention"
- statusLabel(RED) -> "Depasse"
- statusSeverity(GREEN) -> "success"
- statusSeverity(YELLOW) -> "warn"
- statusSeverity(RED) -> "danger"

Scope mapping:
- scopeLabel(SHARED) -> "Commun" with severity "info"
- scopeLabel(PERSONAL) -> "Personnel" with severity "secondary"

Currency formatting: `new Intl.NumberFormat('fr-FR', { style: 'currency', currency: 'EUR' }).format(value)` (matches transactions.ts#formatAmount).

Phase routes already registered in Plan 07: /envelopes, /envelopes/:id.

Component class names locked by Plan 07 routes:
- envelopes.ts -> exports `EnvelopesPage`
- envelope-details.ts -> exports `EnvelopeDetailsPage`

UI-SPEC Copywriting Contract (lines 406-465) is canonical for ALL strings.

**Angular 21 testing imports (REQUIRED):**
- `import { provideRouter } from '@angular/router';` — replaces deprecated RouterTestingModule
- `import { provideHttpClient } from '@angular/common/http';` + `import { provideHttpClientTesting } from '@angular/common/http/testing';` — replaces HttpClientTestingModule (also deprecated in Angular 18+)
- Test bed setup pattern: `TestBed.configureTestingModule({ providers: [provideRouter([]), provideHttpClient(), provideHttpClientTesting(), provideNoopAnimations()] })`
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: EnvelopesPage (/envelopes) — list, filter, status indicators, empty states + envelope-dialog (create/edit)</name>
  <files>frontend/src/app/envelopes/envelopes.ts, frontend/src/app/envelopes/envelopes.spec.ts, frontend/src/app/envelopes/envelope-dialog.ts, frontend/src/app/envelopes/envelope-dialog.spec.ts</files>
  <read_first>
    - frontend/src/app/transactions/transactions.ts (canonical p-table list page with filter bar, header, signals, OnPush)
    - frontend/src/app/transactions/transaction-dialog.ts (canonical p-dialog create/edit pattern with InputNumber, FloatLabel, validation)
    - frontend/src/app/categories/categories.ts (alternative simpler list page reference)
    - frontend/src/app/envelopes/envelope.service.ts (Plan 07 — service to inject)
    - frontend/src/app/envelopes/envelope.types.ts (Plan 07 — types)
    - frontend/src/app/shared/category-selector.ts (Plan 07 — extended for checkbox mode)
    - .planning/phases/06-envelope-budgets/06-UI-SPEC.md (Page 1 + Dialog 1 sections, lines 191-340; Copywriting Contract lines 406-465)
    - frontend/src/app/transactions/transactions.spec.ts (canonical Vitest spec pattern with TestBed + provideRouter + provideHttpClientTesting)
  </read_first>
  <behavior>
**EnvelopesPage:**
- On init: read `?accountId=` and `?includeArchived=` from ActivatedRoute query params, load envelopes via EnvelopeService
- Header shows "Enveloppes" or "Enveloppes — {accountName}" when accountId filter active
- Filter bar: p-select (Compte options, "Tous les comptes" first), p-toggleswitch (Afficher les archivees) — both write back to URL query params
- Table: 8 columns per UI-SPEC (Nom, Compte, Categories, Budget, Consomme, Restant, Statut, Actions)
- Status column shows p-tag (severity from helper) + p-progressbar clamped at 100% display + ARIA label with real percentage + Report tag if rolloverPolicy=CARRY_OVER
- Actions: View (router /envelopes/:id), Personnaliser ce mois (opens allocation dialog), Modifier (opens envelope-dialog edit), Archiver (confirmDialog -> deleteEnvelope)
- Empty states: no envelopes / filtered-empty / no accounts (orphan)
- Errors: load -> "Impossible de charger les enveloppes..." per Copywriting Contract
- WRITE permission gating: hide action buttons (Modifier, Archiver, Personnaliser) when current user has only READ access on the envelope's account (use AccountService.accounts to lookup currentUserAccessLevel)

**EnvelopeDialog (create/edit):**
- Inputs: `mode = 'create' | 'edit'`, `envelope: EnvelopeResponse | null` (for edit), `accounts: AccountResponse[]`, `categories: TreeNode[]`, `lockedAccountId: string | null`
- 5 fields per UI-SPEC: Compte (p-select, disabled in edit), Nom, Categories (CategorySelector checkbox mode), Budget (InputNumber EUR fr-FR), Report (selectButton RESET / CARRY_OVER)
- Scope tag visible once account chosen
- Save button disabled when invalid (name blank, categoryIds empty, budget null/<0, no account)
- Outputs: `saved` emits when save succeeds, `cancelled` emits when user closes
- Error message mapping: 403 / 409 / generic per Copywriting Contract verbatim
  </behavior>
  <action>
This task creates 4 files. Build them in this order: types are already in place (Plan 07).

**File 1: `frontend/src/app/envelopes/envelopes.ts`** — the list page.

Key requirements (mirror `transactions.ts` structure):

- Component selector: `app-envelopes`
- ChangeDetection: OnPush
- Imports: TableModule, ButtonModule, TagModule, ProgressBarModule, SelectModule, MessageModule, ConfirmDialogModule, TooltipModule, ToggleSwitchModule, FormsModule, RouterLink, EnvelopeDialog, EnvelopeAllocationDialog
- Providers: ConfirmationService
- Export class name: `EnvelopesPage` (must match Plan 07 routes)
- Wraps in `<div class="p-8">`
- Header: `<div class="flex items-center justify-between mb-6">` with `<h1 class="text-2xl font-semibold leading-tight">Enveloppes</h1>` (or `Enveloppes &mdash; {{ accountName() }}` when accountId filter active) and `<p-button label="Nouvelle enveloppe" icon="pi pi-plus" (onClick)="openCreateDialog()" />`
- Error block under header: `@if (error()) { <p-message severity="error" [text]="error()!" styleClass="mb-4 w-full" /> }`
- Filter bar: `<div class="bg-surface-50 rounded-lg p-4 mb-4" role="search" aria-label="Filtrer les enveloppes">` containing a `grid grid-cols-1 md:grid-cols-2 gap-4` with:
  - `<p-select [options]="accountFilterOptions()" [(ngModel)]="filterAccountId" optionLabel="label" optionValue="value" [showClear]="true" placeholder="Compte" (onChange)="onFiltersChanged()" />`
  - `<p-toggleswitch [(ngModel)]="includeArchived" inputId="includeArchived" (onChange)="onFiltersChanged()" /><label for="includeArchived" class="ml-2">Afficher les archivees</label>`
- Account filter options: `[{label: 'Tous les comptes', value: null}, ...accounts.map(a => ({label: a.name, value: a.id}))]`
- Table: `<p-table [value]="envelopes()" [loading]="loading()" [stripedRows]="true" sortField="name" [sortOrder]="1" styleClass="p-datatable-sm">` with the 8 columns from UI-SPEC, EXACTLY:
  1. `<th pSortableColumn="name">Nom <p-sortIcon field="name" /></th>` -> `<td>{{ envelope.name }}</td>`
  2. `<th pSortableColumn="bankAccountName">Compte <p-sortIcon field="bankAccountName" /></th>` -> `<td>{{ envelope.bankAccountName }} @if (envelope.scope === 'SHARED') { <p-tag value="Commun" severity="info" styleClass="ml-2" /> }</td>`
  3. Categories column with chips and `+N` overflow per UI-SPEC line 222
  4. Budget column with `tabular-nums` + pencil icon when hasMonthlyOverride
  5. Consomme column with `tabular-nums`
  6. Restant column with `tabular-nums` + `text-red-500` when negative
  7. Status column: `<p-tag [value]="statusLabel(envelope.status)" [severity]="statusSeverity(envelope.status)" />` ABOVE `<p-progressbar [value]="Math.min(100, Math.round(envelope.ratio*100))" [attr.aria-label]="ariaFor(envelope)" styleClass="h-2 mt-1 w-32" />` plus `Report` p-tag when CARRY_OVER
  8. Actions: 4 icon buttons (eye/calendar-plus/pencil/trash), all `[text]="true" [rounded]="true"` with pTooltip; trash is severity="danger"; gate visibility on hasWriteAccess(envelope.bankAccountId)
- ARIA helper: `ariaFor(env) = "Enveloppe " + env.name + ": " + statusAria(env.status) + ", " + Math.round(env.ratio*100) + "% consomme"` where `statusAria(GREEN) = "sur la bonne voie"`, `statusAria(YELLOW) = "attention"`, `statusAria(RED) = "depassee"`
- Empty states (3 variants per UI-SPEC lines 233-259) implemented as separate template blocks gated by computed signals
- Helper functions: `formatAmount(n) = new Intl.NumberFormat('fr-FR', { style: 'currency', currency: 'EUR' }).format(n)`, `statusLabel`, `statusSeverity`, `hasWriteAccess(accountId)` checks AccountService.accounts() for currentUserAccessLevel != READ
- Methods: `openCreateDialog()`, `openEditDialog(env)`, `openAllocationDialog(env)`, `confirmArchive(env)` (using ConfirmationService with archive copy from UI-SPEC line 451), `resetFilters()`, `onFiltersChanged()` (writes back to URL via Router.navigate with relativeTo: route, queryParams: ..., queryParamsHandling: 'merge')
- Use signals (`envelopes`, `loading`, `error`, etc.) and `takeUntilDestroyed(destroyRef)` for subscriptions
- Inject EnvelopeService, AccountService, CategoryService, ConfirmationService, ActivatedRoute, Router, MessageService

**File 2: `frontend/src/app/envelopes/envelope-dialog.ts`** — create/edit dialog.

Key requirements (mirror `transaction-dialog.ts` structure):

- Component selector: `app-envelope-dialog`
- ChangeDetection: OnPush
- Imports: DialogModule, FloatLabelModule, InputTextModule, InputNumberModule, SelectModule, SelectButtonModule, ButtonModule, MessageModule, TagModule, FormsModule, CategorySelector
- Inputs: `visible = input<boolean>(false)`, `mode = input<'create' | 'edit'>('create')`, `envelope = input<EnvelopeResponse | null>(null)`, `accounts = input<AccountResponse[]>([])`, `categoryOptions = input<TreeNode[]>([])`, `lockedAccountId = input<string | null>(null)`
- Outputs: `saved = output<EnvelopeResponse>()`, `cancelled = output<void>()`
- Internal signals: `name`, `selectedAccountId`, `selectedCategoryIds: string[]`, `budget: number | null`, `rolloverPolicy: 'RESET' | 'CARRY_OVER'`, `submitting`, `error`
- Use `effect()` to sync from envelope input on edit mode (preload signals)
- Computed `selectedAccount()` derived from selectedAccountId + accounts
- Computed `isValid()`: `name.trim().length > 0 && selectedCategoryIds.length > 0 && budget != null && budget >= 0 && selectedAccountId != null`
- Header: `<p-dialog [header]="mode() === 'create' ? 'Nouvelle enveloppe' : 'Modifier l''enveloppe'" [(visible)]="open" [modal]="true" [closable]="true" [draggable]="false" [style]="{ width: '36rem' }" (onHide)="cancelled.emit()">`
- 5 fields exactly as UI-SPEC Dialog 1 lines 314-330
- Save button: `<p-button [label]="submitting() ? 'Enregistrement...' : 'Enregistrer'" [loading]="submitting()" [disabled]="!isValid() || submitting()" (onClick)="save()" />`
- Cancel button: `<p-button label="Annuler" [text]="true" severity="secondary" (onClick)="cancelled.emit()" />`
- save() method:
  - Sets submitting(true), clears error
  - On create: `envelopeService.createEnvelope(selectedAccountId, {name, categoryIds: selectedCategoryIds, budget, rolloverPolicy})`
  - On edit: `envelopeService.updateEnvelope(envelope.id, {name, categoryIds: selectedCategoryIds, budget, rolloverPolicy})`
  - On success: emit saved(response), close
  - On error: parse status (403, 409, other) and set `error` signal to the corresponding French copy from UI-SPEC Copywriting Contract
- Hide footer when `submitting=true` is just the loading state — both buttons stay visible

**File 3: `frontend/src/app/envelopes/envelopes.spec.ts`** — Vitest spec for the list page.

Cover at minimum:
- `it('renders status p-tag with severity success when status is GREEN')` — render with envelope status=GREEN, assert `<p-tag>` has severity="success" attribute
- `it('renders status p-tag with severity warn when status is YELLOW')`
- `it('renders status p-tag with severity danger when status is RED')`
- `it('clamps progressbar value at 100 when ratio exceeds 1.0')` — envelope ratio=1.25 -> assert progressbar value=100
- `it('shows the Report tag when rolloverPolicy is CARRY_OVER')`
- `it('renders accountName in header when accountId filter is active')`
- `it('renders no-envelopes empty state when list is empty and no filters applied')` — assert empty state heading "Aucune enveloppe"
- `it('renders filtered-empty state when filters are applied but no match')` — assert "Aucune enveloppe ne correspond"
- `it('renders no-accounts empty state when accounts list is empty')` — assert "Aucun compte disponible"
- `it('hides action buttons when user has READ-only access on the envelope account')`

Test setup MUST use the Angular 21 standalone-providers pattern:

```typescript
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting } from '@angular/common/http/testing';
import { provideNoopAnimations } from '@angular/platform-browser/animations';
// ...

beforeEach(() => {
  TestBed.configureTestingModule({
    imports: [EnvelopesPage],
    providers: [
      provideRouter([]),
      provideHttpClient(),
      provideHttpClientTesting(),
      provideNoopAnimations(),
      // mock services...
    ],
  });
});
```

Do NOT use `RouterTestingModule.withRoutes([])` (deprecated in Angular 21).

**File 4: `frontend/src/app/envelopes/envelope-dialog.spec.ts`** — Vitest spec for the dialog.

Cover at minimum:
- `it('disables save button when name is blank')`
- `it('disables save button when no category selected')`
- `it('disables save button when budget is null')`
- `it('enables save button when all required fields are filled')`
- `it('emits saved when service createEnvelope succeeds')`
- `it('shows 409 error message when service returns conflict')` — verify exact French copy from Copywriting Contract
- `it('shows 403 error message when service returns forbidden')`
- `it('shows generic error message for 500')`
- `it('renders scope tag Commun with severity info when selected account is SHARED')`
- `it('renders scope tag Personnel with severity secondary when selected account is PERSONAL')`
- `it('locks Compte field as disabled in edit mode')`

Each test follows AAA (testing-principles.md): single Act line, no over-mocking. Use `provideRouter([]) + provideHttpClient() + provideHttpClientTesting() + provideNoopAnimations()` (NOT RouterTestingModule).
  </action>
  <verify>
    <automated>cd /home/negus/dev/prosperity/frontend && pnpm test -- --run src/app/envelopes/envelopes.spec.ts src/app/envelopes/envelope-dialog.spec.ts 2>&1 | tail -25</automated>
  </verify>
  <acceptance_criteria>
    - All 4 files exist
    - `grep -c "selector: 'app-envelopes'" frontend/src/app/envelopes/envelopes.ts` returns 1
    - `grep -c "export class EnvelopesPage" frontend/src/app/envelopes/envelopes.ts` returns 1
    - `grep -c "ChangeDetectionStrategy.OnPush" frontend/src/app/envelopes/envelopes.ts` returns 1
    - `grep -c "p-table" frontend/src/app/envelopes/envelopes.ts` returns at least 1
    - `grep -c "p-progressbar" frontend/src/app/envelopes/envelopes.ts` returns at least 1
    - `grep -c "Sur la bonne voie" frontend/src/app/envelopes/envelopes.ts` returns at least 1 (Copywriting Contract)
    - `grep -c "Attention" frontend/src/app/envelopes/envelopes.ts` returns at least 1
    - `grep -c "Depasse\\|Dépassé" frontend/src/app/envelopes/envelopes.ts` returns at least 1
    - `grep -c "Aucune enveloppe" frontend/src/app/envelopes/envelopes.ts` returns at least 1
    - `grep -c "Aucun compte disponible" frontend/src/app/envelopes/envelopes.ts` returns 1
    - `grep -c "Tous les comptes" frontend/src/app/envelopes/envelopes.ts` returns 1
    - `grep -c "Afficher les archiv" frontend/src/app/envelopes/envelopes.ts` returns 1
    - `grep -c "selector: 'app-envelope-dialog'" frontend/src/app/envelopes/envelope-dialog.ts` returns 1
    - `grep -c "export class EnvelopeDialog" frontend/src/app/envelopes/envelope-dialog.ts` returns 1
    - `grep -c "selectionMode=\"checkbox\"" frontend/src/app/envelopes/envelope-dialog.ts` returns 1
    - `grep -c "Une categorie selectionnee appartient deja\\|Une catégorie sélectionnée appartient déjà" frontend/src/app/envelopes/envelope-dialog.ts` returns 1 (409 message)
    - `grep -c "Vous n'avez pas les droits\\|Vous n''avez pas les droits" frontend/src/app/envelopes/envelope-dialog.ts` returns at least 1 (403 message)
    - `grep -c "Remise" frontend/src/app/envelopes/envelope-dialog.ts` returns 1 (RESET label)
    - `grep -c "Report du solde" frontend/src/app/envelopes/envelope-dialog.ts` returns 1 (CARRY_OVER label)
    - `grep -c "provideRouter" frontend/src/app/envelopes/envelopes.spec.ts` returns at least 1
    - `grep -c "provideRouter" frontend/src/app/envelopes/envelope-dialog.spec.ts` returns at least 1
    - `grep -c "RouterTestingModule" frontend/src/app/envelopes/envelopes.spec.ts` returns 0 (deprecated; banned)
    - `grep -c "RouterTestingModule" frontend/src/app/envelopes/envelope-dialog.spec.ts` returns 0
    - `pnpm test -- --run src/app/envelopes/envelopes.spec.ts src/app/envelopes/envelope-dialog.spec.ts` exits 0 with all tests passing (at least 10 tests in envelopes.spec.ts and 11 in envelope-dialog.spec.ts)
  </acceptance_criteria>
  <done>EnvelopesPage and EnvelopeDialog components built per UI-SPEC; status mapping/empty states/error mapping all in place; component specs cover behaviour required by 06-VALIDATION.md and 06-RESEARCH.md test map; specs use provideRouter (not RouterTestingModule).</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: EnvelopeDetailsPage (/envelopes/:id) + EnvelopeAllocationDialog + service spec</name>
  <files>frontend/src/app/envelopes/envelope-details.ts, frontend/src/app/envelopes/envelope-details.spec.ts, frontend/src/app/envelopes/envelope-allocation-dialog.ts, frontend/src/app/envelopes/envelope-allocation-dialog.spec.ts, frontend/src/app/envelopes/envelope.service.spec.ts</files>
  <read_first>
    - frontend/src/app/accounts/account-details.ts (canonical /entity/:id details page if exists; otherwise transactions.ts pattern)
    - frontend/src/app/transactions/transaction-dialog.ts (DatePicker month-view reference if used)
    - frontend/src/app/envelopes/envelopes.ts (Task 1 output — reuse helpers)
    - frontend/src/app/envelopes/envelope.service.ts (Plan 07)
    - .planning/phases/06-envelope-budgets/06-UI-SPEC.md (Page 2 lines 263-302; Dialog 2 lines 344-364; Copywriting Contract)
  </read_first>
  <behavior>
**EnvelopeDetailsPage:**
- Reads `/envelopes/:id` from ActivatedRoute paramMap
- Loads envelope via service.getEnvelope(id)
- Loads history via service.getHistory(id) (12 entries)
- Header: back link "Retour aux enveloppes", h1 = envelope.name, sub-line = bankAccountName + scope label
- Right header cluster: status p-tag for current month, "Personnaliser ce mois" button (opens allocation dialog), "Modifier" button (opens envelope-dialog edit), trash icon (confirmDialog -> deleteEnvelope -> redirect /envelopes)
- Summary card: Budget effectif / Consomme / Restant in 3-col grid + full-width progressbar
- 12-month history p-table: Mois (DatePipe MMMM yyyy fr-FR), Budget effectif, Consomme, Restant, Statut (mini p-tag + narrow progressbar) — sort default month DESC
- Each row clickable to /accounts/{accountId}/transactions?dateFrom=...&dateTo=...
- Empty history state when array empty per UI-SPEC line 293-299

**EnvelopeAllocationDialog:**
- Inputs: `visible`, `envelope`, `existing: EnvelopeAllocationResponse | null` (for edit)
- Form: month (DatePicker view=month), allocatedAmount (InputNumber EUR fr-FR)
- List of existing overrides below form (small p-table with Mois, Budget, delete action)
- save() calls createAllocation or updateAllocation; emits saved
- delete on row in list opens ConfirmDialog with exact copy from UI-SPEC line 453

**EnvelopeService spec:**
- Tests each public method using `provideHttpClient()` + `provideHttpClientTesting()` + `HttpTestingController.expectOne`
- Verifies URL, method (GET/POST/PUT/DELETE), and body for createEnvelope, updateEnvelope, deleteEnvelope, getHistory, listAllocations, createAllocation, updateAllocation, deleteAllocation, loadEnvelopes (with and without filters), loadEnvelopesForAccount
  </behavior>
  <action>
Create the 5 files following the patterns established in Task 1.

**File 1: `frontend/src/app/envelopes/envelope-details.ts`** — page component named `EnvelopeDetailsPage`.

Mandatory structure:
- selector: `app-envelope-details`, OnPush, takeUntilDestroyed pattern
- Inject ActivatedRoute, Router, EnvelopeService, ConfirmationService, MessageService
- On init: read paramMap.get('id'), load envelope + history concurrently (forkJoin or parallel calls)
- Wraps in `<div class="p-8">`
- Header block per UI-SPEC line 267-273
- Summary card per UI-SPEC line 275-281: 3-col grid + progressbar
- Overrides section: only renders when `monthlyOverrides().length > 0`
- 12-month history p-table per UI-SPEC line 287-291; rows clickable to navigate to transactions filtered by month + envelope categories
- Empty state per UI-SPEC line 292-299 ("Pas encore d'historique") only when ALL 12 entries have consumed=0 AND no allocations exist
- Helpers reuse from envelopes.ts (statusLabel, statusSeverity, formatAmount, scopeLabel) — either duplicate inline or extract to a util file. PREFER inline duplication for atomic plans (testing-principles.md DAMP > DRY).
- Confirm archive dialog uses copy from UI-SPEC line 449-451 verbatim

**File 2: `frontend/src/app/envelopes/envelope-details.spec.ts`** covering at minimum:
- `it('renders the envelope name in the page header')`
- `it('renders 12 rows in the history table')` — mock service.getHistory with 12 entries
- `it('renders Pas encore d historique empty state when all months have zero consumed')`
- `it('shows Personnaliser ce mois button in the header')`
- `it('opens edit dialog when Modifier button clicked')`
- `it('navigates to /envelopes after successful delete confirmation')`

Test setup uses `provideRouter([]) + provideHttpClient() + provideHttpClientTesting() + provideNoopAnimations()` (NOT RouterTestingModule).

**File 3: `frontend/src/app/envelopes/envelope-allocation-dialog.ts`** — component `EnvelopeAllocationDialog`.

Mandatory structure:
- selector: `app-envelope-allocation-dialog`, OnPush
- Inputs: `visible`, `envelope: EnvelopeResponse | null`, `existing: EnvelopeAllocationResponse | null`
- Outputs: `saved`, `cancelled`
- Imports: DialogModule, DatePickerModule, InputNumberModule, ButtonModule, TableModule, MessageModule, TooltipModule, ConfirmDialogModule, FormsModule
- Header per UI-SPEC line 348: `Personnaliser le budget d'un mois`
- Form: month (DatePicker view=month, dateFormat="MM yy"), allocatedAmount
- Convert Date <-> "yyyy-MM" string before sending to service (since the backend expects YearMonth)
- List existing overrides below form (loads via service.listAllocations on input change), each row has delete button with confirmation
- Save calls service.createAllocation or updateAllocation
- Delete row calls service.deleteAllocation; on success refresh list

**File 4: `frontend/src/app/envelopes/envelope-allocation-dialog.spec.ts`** covering at minimum:
- `it('defaults month to current month when opened without context')`
- `it('disables save when allocatedAmount is null')`
- `it('emits saved when service createAllocation succeeds')`
- `it('shows 409 error when month already has an allocation')` — exact copy from UI-SPEC Copywriting Contract
- `it('lists existing overrides ordered by month')`

Test setup uses provideRouter (not RouterTestingModule).

**File 5: `frontend/src/app/envelopes/envelope.service.spec.ts`** covering each service method:
- `it('GET /api/envelopes returns envelopes')`
- `it('GET /api/envelopes?accountId=X passes accountId query param')`
- `it('GET /api/envelopes?includeArchived=true passes flag')`
- `it('GET /api/accounts/{id}/envelopes calls per-account endpoint')`
- `it('POST /api/accounts/{id}/envelopes sends create body')`
- `it('PUT /api/envelopes/{id} sends update body')`
- `it('DELETE /api/envelopes/{id} returns void')`
- `it('GET /api/envelopes/{id}/history?month=2026-04 passes month param')`
- `it('GET /api/envelopes/{id}/allocations returns list')`
- `it('POST /api/envelopes/{id}/allocations sends body')`
- `it('PUT /api/envelopes/allocations/{id} sends body')`
- `it('DELETE /api/envelopes/allocations/{id} returns void')`

Use `provideHttpClient()` + `provideHttpClientTesting()` (the standalone-providers Angular 21 pattern; HttpClientTestingModule is deprecated). Each test has Arrange (set up controller via `TestBed.inject(HttpTestingController)`), Act (call service method, subscribe), Assert (req.method + req.url + req.request.body checks).

```typescript
beforeEach(() => {
  TestBed.configureTestingModule({
    providers: [
      EnvelopeService,
      provideHttpClient(),
      provideHttpClientTesting(),
    ],
  });
  http = TestBed.inject(HttpTestingController);
  service = TestBed.inject(EnvelopeService);
});
```
  </action>
  <verify>
    <automated>cd /home/negus/dev/prosperity/frontend && pnpm test -- --run src/app/envelopes 2>&1 | tail -30</automated>
  </verify>
  <acceptance_criteria>
    - All 5 files exist
    - `grep -c "export class EnvelopeDetailsPage" frontend/src/app/envelopes/envelope-details.ts` returns 1
    - `grep -c "export class EnvelopeAllocationDialog" frontend/src/app/envelopes/envelope-allocation-dialog.ts` returns 1
    - `grep -c "Retour aux enveloppes" frontend/src/app/envelopes/envelope-details.ts` returns 1
    - `grep -c "Personnaliser ce mois" frontend/src/app/envelopes/envelope-details.ts` returns 1
    - `grep -c "Pas encore d'historique\\|Pas encore d historique" frontend/src/app/envelopes/envelope-details.ts` returns 1
    - `grep -c "Personnaliser le budget" frontend/src/app/envelopes/envelope-allocation-dialog.ts` returns 1
    - `grep -c "provideHttpClientTesting" frontend/src/app/envelopes/envelope.service.spec.ts` returns at least 1
    - `grep -c "expectOne" frontend/src/app/envelopes/envelope.service.spec.ts` returns at least 11 (one per route)
    - `grep -c "/api/envelopes" frontend/src/app/envelopes/envelope.service.spec.ts` returns at least 8
    - `grep -c "RouterTestingModule" frontend/src/app/envelopes/envelope-details.spec.ts` returns 0
    - `grep -c "RouterTestingModule" frontend/src/app/envelopes/envelope-allocation-dialog.spec.ts` returns 0
    - `grep -c "provideRouter" frontend/src/app/envelopes/envelope-details.spec.ts` returns at least 1
    - `pnpm test -- --run src/app/envelopes` exits 0; vitest summary shows all envelope-related tests passing (no skipped, no failures)
    - `pnpm lint -- --max-warnings 0` exits 0
  </acceptance_criteria>
  <done>EnvelopeDetailsPage, EnvelopeAllocationDialog, service spec all implemented, all envelope frontend tests passing, lint clean, no deprecated RouterTestingModule references.</done>
</task>

<task type="auto" tdd="false">
  <name>Task 3: Flip 06-VALIDATION.md nyquist_compliant: true (final acceptance gate of Plan 08)</name>
  <files>.planning/phases/06-envelope-budgets/06-VALIDATION.md</files>
  <read_first>
    - .planning/phases/06-envelope-budgets/06-VALIDATION.md (current state — wave_0_complete should already be true from Plan 03)
  </read_first>
  <action>
After Tasks 1 + 2 are complete and `pnpm test -- --run src/app/envelopes` exits 0 with all real assertions:

1. Open `.planning/phases/06-envelope-budgets/06-VALIDATION.md`
2. In the YAML frontmatter, change `nyquist_compliant: false` to `nyquist_compliant: true`
3. In the Validation Sign-Off section at the bottom, flip the checkbox `[ ] nyquist_compliant: true set in frontmatter` to `[x] nyquist_compliant: true set in frontmatter (FLIPPED by Plan 08 — pnpm test src/app/envelopes green; backend bodies green from Plan 06)`
4. Update the "Approval:" line to: `**Approval:** Phase 6 validation complete — Wave 0 scaffolding (Plan 03) + backend bodies green (Plan 06) + frontend specs green (Plan 08). Ready for /gsd:verify-work.`

Do NOT make any other edits to this file. Do NOT touch the Wave 0 Requirements or Per-Task Verification Map sections — those are already correct from Plan 03's Task 3.
  </action>
  <verify>
    <automated>grep -c "nyquist_compliant: true" .planning/phases/06-envelope-budgets/06-VALIDATION.md</automated>
  </verify>
  <acceptance_criteria>
    - `grep -c "nyquist_compliant: true" .planning/phases/06-envelope-budgets/06-VALIDATION.md` returns 1
    - `grep -c "nyquist_compliant: false" .planning/phases/06-envelope-budgets/06-VALIDATION.md` returns 0
    - `grep -c "wave_0_complete: true" .planning/phases/06-envelope-budgets/06-VALIDATION.md` returns 1 (preserved from Plan 03)
    - `grep -c "Phase 6 validation complete" .planning/phases/06-envelope-budgets/06-VALIDATION.md` returns 1
  </acceptance_criteria>
  <done>06-VALIDATION.md frontmatter has both wave_0_complete: true and nyquist_compliant: true; Validation Sign-Off section reflects Plan 08 completion; ready for /gsd:verify-work.</done>
</task>

<task type="checkpoint:human-verify" gate="blocking">
  <name>Task 4: Visual + interactive verification of Phase 6 envelope UI</name>
  <files></files>
  <action>
Present the envelope budgets interface for human verification. The user will exercise the complete envelope flow through the browser.
  </action>
  <verify>User confirms approval after walking through the 22-step UAT script below</verify>
  <done>User types "approved" after verifying the envelope UI matches the UI-SPEC contract on every step</done>
  <what-built>
Plan 06 backend (envelopes API + allocations API) + Plan 07/08 frontend (sidebar entry, /envelopes list page with status badges, envelope create/edit dialog with multi-category select, /envelopes/:id details page with 12-month history, monthly override dialog).
  </what-built>
  <how-to-verify>
1. Start the stack: `docker compose up -d` and wait for healthy.
2. Open http://localhost (Caddy) — login as the test user (or create one via setup wizard).
3. Open `/categories` and confirm the seed taxonomy is present (Phase 4 already did this; this step is a sanity check).
4. Open `/accounts` and create at least one PERSONAL account named "Test Perso" if it doesn't exist; create at least one SHARED account named "Test Commun" if it doesn't exist.
5. Click the new "Enveloppes" entry in the sidebar — page loads at `/envelopes`.
6. Empty state: confirm the heading "Aucune enveloppe" + create CTA renders when no envelopes exist.
7. Click "Nouvelle enveloppe":
   - Select "Test Perso" in Compte field — confirm scope badge "Personnel" appears.
   - Switch to "Test Commun" — confirm scope badge changes to "Commun" (info severity).
   - Type a name "Vie quotidienne".
   - Open Categories tree-select — verify checkboxes appear, parent ticking ticks children.
   - Select 2 categories (e.g. Alimentation > Courses, Transport > Carburant).
   - Set budget to 500.
   - Choose "Report du solde" rollover.
   - Save — dialog closes, row appears in the table.
8. In the table:
   - Confirm columns: Nom, Compte (with Commun tag), Categories chips (with +N if 4+), Budget (500,00 €), Consomme (0,00 €), Restant (500,00 €), Statut (Sur la bonne voie + green progressbar at 0%), Report tag (info), Actions.
   - Hover trash button — tooltip "Archiver l'enveloppe".
9. Open `/transactions` for the same account and create a few transactions in the linked categories (one for -200, one for -150, one for -100 — total 450€ spending).
10. Return to `/envelopes` — confirm the consumed updates to 450,00 €, restant 50,00 €, statut "Attention" (yellow, 90% ratio).
11. Add another transaction for -100 (total 550€) — refresh `/envelopes` and confirm statut "Depasse" (red, ~110% ratio), restant -50,00 € (red text), progressbar visually at 100% but ARIA reads ~110%.
12. Click the eye icon on the envelope row -> `/envelopes/:id`.
13. On details page:
    - Verify header (back link, name, sub-line with account + scope).
    - Verify summary card (Budget, Consomme, Restant) with current month values.
    - Verify 12-month history table — current month row shows the same numbers, previous months show 0,00 €.
14. Click "Personnaliser ce mois" — month dialog opens, defaults to current month. Set budget to 800. Save.
15. Confirm the list page now shows pencil icon next to the budget (hover tooltip "Budget personnalise ce mois").
16. Open the override dialog again from list — confirm the existing override appears in the dialog's overrides list. Click delete — confirm copy "Supprimer le budget personnalise de {month} ?" appears. Confirm.
17. Edit the envelope, change the categories (remove one, add another). Confirm save works and chips update.
18. Try to create a SECOND envelope on the SAME account that links to a category already used — confirm 409 error message renders verbatim: "Une categorie selectionnee appartient deja a une autre enveloppe de ce compte. Choisissez des categories libres."
19. Archive the envelope (trash button) — confirm copy in confirmation dialog matches UI-SPEC. After confirm, envelope disappears from list. Toggle "Afficher les archivees" — envelope reappears in the list with muted styling.
20. Sidebar verification: click "Comptes" then "Categories" then "Enveloppes" — each route highlights the active sidebar entry with the indigo left border.
21. Theme: open browser dev tools, toggle prefers-color-scheme between light and dark — verify status tags maintain AA contrast in both modes (Aura preset handles this; a quick visual sanity check).
22. Keyboard: Tab through the create-envelope dialog — order should be Compte -> Nom -> Categories -> Budget -> Rollover -> Annuler -> Enregistrer. Esc closes dialog.

Pass criteria: all 22 steps behave as described. Any deviation = fail; report which step + actual behaviour.
  </how-to-verify>
  <resume-signal>Type "approved" or describe issues to address before phase verification</resume-signal>
</task>

</tasks>

<verification>
- `pnpm test -- --run src/app/envelopes` exits 0 with all envelope-related test files passing.
- `pnpm lint -- --max-warnings 0` exits 0.
- `pnpm exec tsc --noEmit -p tsconfig.app.json` exits 0 (no dangling type errors).
- The visual checkpoint (Task 4) passes.
- 06-VALIDATION.md `nyquist_compliant: true` and `wave_0_complete: true` are both set after Task 3 runs.
- No spec file references the deprecated `RouterTestingModule` (replaced with `provideRouter([])`).
</verification>

<success_criteria>
- 4 component files (envelopes, envelope-dialog, envelope-details, envelope-allocation-dialog) implement UI-SPEC verbatim.
- 5 spec files cover the test rows from 06-VALIDATION.md / 06-RESEARCH.md test map.
- Status enum mapping (server) -> p-tag severity (frontend) is 1:1 — frontend never recomputes thresholds.
- All Copywriting Contract strings present verbatim (with apostrophe variants — French copy may use either ' or ').
- Sidebar entry navigates to /envelopes; routes lazy-load components.
- 06-VALIDATION.md flipped to nyquist_compliant: true.
- No spec uses RouterTestingModule.
- Manual checkpoint passes for visual/interactive verification.
</success_criteria>

<output>
After completion, create `.planning/phases/06-envelope-budgets/06-08-frontend-pages-SUMMARY.md`.
</output>
