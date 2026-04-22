import {
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
  computed,
  effect,
  inject,
  signal,
} from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { TreeNode, ConfirmationService } from 'primeng/api';
import { TableModule } from 'primeng/table';
import { ButtonModule } from 'primeng/button';
import { TagModule } from 'primeng/tag';
import { ProgressBarModule } from 'primeng/progressbar';
import { SelectModule } from 'primeng/select';
import { MessageModule } from 'primeng/message';
import { ConfirmDialogModule } from 'primeng/confirmdialog';
import { TooltipModule } from 'primeng/tooltip';
import { ToggleSwitchModule } from 'primeng/toggleswitch';
import { EnvelopeService } from './envelope.service';
import {
  EnvelopeResponse,
  EnvelopeStatus,
} from './envelope.types';
import { AccountService } from '../accounts/account.service';
import { AccountResponse } from '../accounts/account.types';
import { CategoryService } from '../categories/category.service';
import { EnvelopeDialog } from './envelope-dialog';
import { EnvelopeAllocationDialog } from './envelope-allocation-dialog';

interface AccountOption {
  label: string;
  value: string | null;
}

@Component({
  selector: 'app-envelopes',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    FormsModule,
    RouterLink,
    TableModule,
    ButtonModule,
    TagModule,
    ProgressBarModule,
    SelectModule,
    MessageModule,
    ConfirmDialogModule,
    TooltipModule,
    ToggleSwitchModule,
    EnvelopeDialog,
    EnvelopeAllocationDialog,
  ],
  providers: [ConfirmationService],
  template: `
    <div class="p-8">
      <!-- Header -->
      <div class="flex items-center justify-between mb-6">
        @if (accountFilterId()) {
          <h1 class="text-2xl font-semibold leading-tight">
            Enveloppes &mdash; {{ filteredAccountName() }}
          </h1>
        } @else {
          <h1 class="text-2xl font-semibold leading-tight">Enveloppes</h1>
        }
        @if (hasAccounts()) {
          <p-button
            label="Nouvelle enveloppe"
            icon="pi pi-plus"
            (onClick)="openCreateDialog()"
          />
        }
      </div>

      <!-- Error -->
      @if (error()) {
        <p-message severity="error" [text]="error()!" styleClass="mb-4 w-full" />
      }

      <!-- Filter bar -->
      @if (hasAccounts()) {
        <div
          class="bg-surface-50 rounded-lg p-4 mb-4"
          role="search"
          aria-label="Filtrer les enveloppes"
        >
          <div class="grid grid-cols-1 md:grid-cols-2 gap-4 items-center">
            <p-select
              [options]="accountFilterOptions()"
              [(ngModel)]="filterAccountId"
              optionLabel="label"
              optionValue="value"
              [showClear]="true"
              placeholder="Tous les comptes"
              (onChange)="onFiltersChanged()"
              (onClear)="onFilterAccountCleared()"
              styleClass="w-full"
              aria-label="Compte"
            />
            <div class="flex items-center">
              <p-toggleswitch
                [(ngModel)]="includeArchived"
                inputId="includeArchived"
                (onChange)="onFiltersChanged()"
              />
              <label for="includeArchived" class="ml-2">Afficher les archivees</label>
            </div>
          </div>
        </div>
      }

      <!-- Empty: no accounts at all (orphan) -->
      @if (!hasAccounts() && !loading()) {
        <div role="status" class="text-center py-12">
          <h2 class="text-lg font-semibold mb-2">Aucun compte disponible</h2>
          <p class="text-muted-color mb-4">
            Creez d'abord un compte bancaire pour pouvoir definir des enveloppes.
          </p>
          <p-button
            label="Aller aux comptes"
            icon="pi pi-wallet"
            [routerLink]="['/accounts']"
          />
        </div>
      }

      <!-- Empty: filtered to nothing -->
      @else if (
        hasAccounts() && !loading() && envelopes().length === 0 && filtersActive()
      ) {
        <div role="status" class="text-center py-12">
          <h2 class="text-lg font-semibold mb-2">Aucune enveloppe ne correspond</h2>
          <p class="text-muted-color mb-4">
            Essayez un autre compte ou reinitialisez les filtres.
          </p>
          <p-button
            label="Reinitialiser les filtres"
            severity="secondary"
            [text]="true"
            (onClick)="resetFilters()"
          />
        </div>
      }

      <!-- Empty: no envelopes yet (unfiltered) -->
      @else if (
        hasAccounts() && !loading() && envelopes().length === 0 && !filtersActive()
      ) {
        <div role="status" class="text-center py-12">
          <i class="pi pi-inbox text-5xl text-muted-color mb-4 block" aria-hidden="true"></i>
          <h2 class="text-lg font-semibold mb-2">Aucune enveloppe</h2>
          <p class="text-muted-color mb-4">
            Creez votre premiere enveloppe pour suivre votre budget par categorie sur un compte.
          </p>
          <p-button
            label="Nouvelle enveloppe"
            icon="pi pi-plus"
            (onClick)="openCreateDialog()"
          />
        </div>
      }

      <!-- Table -->
      @else if (hasAccounts() && envelopes().length > 0) {
        <p-table
          [value]="envelopes()"
          [loading]="loading()"
          [stripedRows]="true"
          sortField="name"
          [sortOrder]="1"
          styleClass="p-datatable-sm"
        >
          <ng-template pTemplate="header">
            <tr>
              <th pSortableColumn="name" scope="col">
                Nom <p-sortIcon field="name" />
              </th>
              <th pSortableColumn="bankAccountName" scope="col">
                Compte <p-sortIcon field="bankAccountName" />
              </th>
              <th scope="col">Categories</th>
              <th pSortableColumn="effectiveBudget" scope="col" class="text-right">
                Budget <p-sortIcon field="effectiveBudget" />
              </th>
              <th pSortableColumn="consumed" scope="col" class="text-right">
                Consomme <p-sortIcon field="consumed" />
              </th>
              <th pSortableColumn="available" scope="col" class="text-right">
                Restant <p-sortIcon field="available" />
              </th>
              <th pSortableColumn="ratio" scope="col">
                Statut <p-sortIcon field="ratio" />
              </th>
              <th scope="col">Actions</th>
            </tr>
          </ng-template>
          <ng-template pTemplate="body" let-envelope>
            <tr [class.text-muted-color]="envelope.archived">
              <td>{{ envelope.name }}</td>
              <td>
                {{ envelope.bankAccountName }}
                @if (envelope.scope === 'SHARED') {
                  <p-tag value="Commun" severity="info" styleClass="ml-2" />
                }
              </td>
              <td>
                @for (cat of categoriesToShow(envelope); track cat.id) {
                  <p-tag
                    [value]="cat.name"
                    severity="secondary"
                    styleClass="mr-1 mb-1"
                  />
                }
                @if (envelope.categories.length > 3) {
                  <p-tag
                    [value]="'+' + (envelope.categories.length - 3)"
                    severity="secondary"
                    [pTooltip]="categoryTooltip(envelope)"
                  />
                }
              </td>
              <td class="text-right">
                <span class="tabular-nums">{{ formatAmount(envelope.effectiveBudget) }}</span>
                @if (envelope.hasMonthlyOverride) {
                  <i
                    class="pi pi-pencil text-xs ml-1 text-muted-color"
                    pTooltip="Budget personnalise ce mois"
                    aria-hidden="true"
                  ></i>
                }
              </td>
              <td class="text-right">
                <span class="tabular-nums">{{ formatAmount(envelope.consumed) }}</span>
              </td>
              <td class="text-right">
                <span
                  class="tabular-nums"
                  [class.text-red-500]="envelope.available < 0"
                >
                  {{ formatAmount(envelope.available) }}
                </span>
              </td>
              <td>
                <div class="flex items-center gap-2">
                  <p-tag
                    [value]="statusLabel(envelope.status)"
                    [severity]="statusSeverity(envelope.status)"
                  />
                  @if (envelope.rolloverPolicy === 'CARRY_OVER') {
                    <p-tag
                      value="Report"
                      severity="info"
                      [rounded]="true"
                      pTooltip="Le solde du mois precedent est reporte"
                    />
                  }
                </div>
                <p-progressbar
                  [value]="clampedPercent(envelope)"
                  [attr.aria-label]="ariaFor(envelope)"
                  styleClass="h-2 mt-1 w-32"
                />
              </td>
              <td>
                <div class="flex gap-1">
                  <p-button
                    icon="pi pi-eye"
                    [text]="true"
                    [rounded]="true"
                    severity="secondary"
                    pTooltip="Voir l'historique"
                    [routerLink]="['/envelopes', envelope.id]"
                    [attr.aria-label]="historyLabel(envelope.name)"
                  />
                  @if (hasWriteAccess(envelope.bankAccountId)) {
                    <p-button
                      icon="pi pi-calendar-plus"
                      [text]="true"
                      [rounded]="true"
                      severity="secondary"
                      pTooltip="Personnaliser ce mois"
                      (onClick)="openAllocationDialog(envelope)"
                      [attr.aria-label]="'Personnaliser le budget ce mois pour ' + envelope.name"
                    />
                    <p-button
                      icon="pi pi-pencil"
                      [text]="true"
                      [rounded]="true"
                      severity="secondary"
                      pTooltip="Modifier l'enveloppe"
                      (onClick)="openEditDialog(envelope)"
                      [attr.aria-label]="'Modifier ' + envelope.name"
                    />
                    <p-button
                      icon="pi pi-trash"
                      [text]="true"
                      [rounded]="true"
                      severity="danger"
                      pTooltip="Archiver l'enveloppe"
                      (onClick)="confirmArchive(envelope)"
                      [attr.aria-label]="'Archiver ' + envelope.name"
                    />
                  }
                </div>
              </td>
            </tr>
          </ng-template>
        </p-table>
      }

      <p-confirmdialog />

      @if (showDialog()) {
        <app-envelope-dialog
          [visible]="true"
          [mode]="dialogMode()"
          [envelope]="editingEnvelope()"
          [accounts]="accountsForDialog()"
          [categoryOptions]="categoryOptions()"
          [lockedAccountId]="lockedAccountId()"
          (saved)="onDialogSaved()"
          (cancelled)="closeDialog()"
        />
      }

      @if (showAllocationDialog()) {
        <app-envelope-allocation-dialog
          [visible]="true"
          [envelope]="allocationEnvelope()"
          (saved)="onAllocationSaved()"
          (cancelled)="closeAllocationDialog()"
        />
      }
    </div>
  `,
})
export class EnvelopesPage {
  private readonly envelopeService = inject(EnvelopeService);
  private readonly accountService = inject(AccountService);
  private readonly categoryService = inject(CategoryService);
  private readonly confirmationService = inject(ConfirmationService);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly destroyRef = inject(DestroyRef);

  protected readonly envelopes = signal<EnvelopeResponse[]>([]);
  protected readonly loading = signal<boolean>(true);
  protected readonly error = signal<string | null>(null);
  protected readonly categoryOptions = signal<TreeNode[]>([]);

  // URL-driven filter state
  protected readonly accountFilterId = signal<string | null>(null);
  protected readonly includeArchivedSignal = signal<boolean>(false);

  protected filterAccountId: string | null = null;
  protected includeArchived = false;

  // Dialog state
  protected readonly showDialog = signal<boolean>(false);
  protected readonly editingEnvelope = signal<EnvelopeResponse | null>(null);
  protected readonly dialogMode = signal<'create' | 'edit'>('create');
  protected readonly lockedAccountId = signal<string | null>(null);

  // Allocation dialog state
  protected readonly showAllocationDialog = signal<boolean>(false);
  protected readonly allocationEnvelope = signal<EnvelopeResponse | null>(null);

  // Derived
  protected readonly accounts = this.accountService.accounts;

  protected readonly hasAccounts = computed(() => this.accounts().length > 0);

  protected readonly accountsForDialog = computed(() =>
    this.accounts().filter(
      (a) => !a.archived && a.currentUserAccessLevel !== 'READ',
    ),
  );

  protected readonly accountFilterOptions = computed<AccountOption[]>(() => [
    { label: 'Tous les comptes', value: null },
    ...this.accounts().map((a) => ({ label: a.name, value: a.id })),
  ]);

  protected readonly filteredAccountName = computed(() => {
    const id = this.accountFilterId();
    if (!id) return '';
    return this.accounts().find((a) => a.id === id)?.name ?? '';
  });

  protected readonly filtersActive = computed(
    () => this.accountFilterId() !== null || this.includeArchivedSignal(),
  );

  constructor() {
    // Load accounts for filter dropdown + access checks.
    this.accountService
      .loadAccounts()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe();

    // Load category options for dialogs.
    this.categoryService
      .loadCategories()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe((cats) => {
        const roots = cats.filter((c) => !c.parentId);
        const nodes: TreeNode[] = roots.map((root) => {
          const children = cats.filter((c) => c.parentId === root.id);
          return {
            key: root.id,
            label: root.name,
            data: root.id,
            children:
              children.length > 0
                ? children.map((child) => ({
                    key: child.id,
                    label: child.name,
                    data: child.id,
                  }))
                : undefined,
          };
        });
        this.categoryOptions.set(nodes);
      });

    // Pick up filters from URL query params.
    this.route.queryParamMap
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe((params) => {
        const accountId = params.get('accountId');
        const includeArchived = params.get('includeArchived') === 'true';
        this.accountFilterId.set(accountId);
        this.includeArchivedSignal.set(includeArchived);
        this.filterAccountId = accountId;
        this.includeArchived = includeArchived;
        this.loadEnvelopes();
      });

    // Ensure archived toggle is disabled when no filters active — we still load.
    effect(() => {
      // Track filters for loader; actual fetch triggered in subscribe above
      void this.accountFilterId();
      void this.includeArchivedSignal();
    });
  }

  private loadEnvelopes(): void {
    this.loading.set(true);
    this.error.set(null);

    const filters = {
      accountId: this.accountFilterId() ?? undefined,
      includeArchived: this.includeArchivedSignal(),
    };

    this.envelopeService
      .loadEnvelopes(filters)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (list) => {
          this.envelopes.set(list);
          this.loading.set(false);
        },
        error: () => {
          this.loading.set(false);
          this.error.set(
            'Impossible de charger les enveloppes. Verifiez votre connexion et reessayez.',
          );
        },
      });
  }

  protected onFiltersChanged(): void {
    this.router.navigate([], {
      relativeTo: this.route,
      queryParams: {
        accountId: this.filterAccountId,
        includeArchived: this.includeArchived ? 'true' : null,
      },
      queryParamsHandling: 'merge',
    });
  }

  protected onFilterAccountCleared(): void {
    this.filterAccountId = null;
    this.onFiltersChanged();
  }

  protected resetFilters(): void {
    this.filterAccountId = null;
    this.includeArchived = false;
    this.router.navigate([], {
      relativeTo: this.route,
      queryParams: {},
    });
  }

  protected openCreateDialog(): void {
    this.editingEnvelope.set(null);
    this.dialogMode.set('create');
    this.lockedAccountId.set(this.accountFilterId());
    this.showDialog.set(true);
  }

  protected openEditDialog(envelope: EnvelopeResponse): void {
    this.editingEnvelope.set(envelope);
    this.dialogMode.set('edit');
    this.lockedAccountId.set(envelope.bankAccountId);
    this.showDialog.set(true);
  }

  protected openAllocationDialog(envelope: EnvelopeResponse): void {
    this.allocationEnvelope.set(envelope);
    this.showAllocationDialog.set(true);
  }

  protected closeDialog(): void {
    this.showDialog.set(false);
    this.editingEnvelope.set(null);
    this.lockedAccountId.set(null);
  }

  protected closeAllocationDialog(): void {
    this.showAllocationDialog.set(false);
    this.allocationEnvelope.set(null);
  }

  protected onDialogSaved(): void {
    this.closeDialog();
    this.loadEnvelopes();
  }

  protected onAllocationSaved(): void {
    this.closeAllocationDialog();
    this.loadEnvelopes();
  }

  protected confirmArchive(envelope: EnvelopeResponse): void {
    this.confirmationService.confirm({
      header: 'Archiver l\'enveloppe',
      message:
        `Etes-vous sur de vouloir archiver l'enveloppe "${envelope.name}" ? Son historique reste consultable dans les archives mais elle ne sera plus affichee par defaut.`,
      acceptLabel: 'Archiver',
      rejectLabel: 'Annuler',
      acceptButtonProps: { severity: 'danger' },
      accept: () => {
        this.envelopeService
          .deleteEnvelope(envelope.id)
          .pipe(takeUntilDestroyed(this.destroyRef))
          .subscribe({
            next: () => this.loadEnvelopes(),
            error: () =>
              this.error.set(
                'Impossible d\'archiver l\'enveloppe. Veuillez reessayer.',
              ),
          });
      },
    });
  }

  protected hasWriteAccess(accountId: string): boolean {
    const account = this.accounts().find((a) => a.id === accountId);
    if (!account) return false;
    return account.currentUserAccessLevel !== 'READ';
  }

  protected statusLabel(status: EnvelopeStatus): string {
    switch (status) {
      case 'GREEN':
        return 'Sur la bonne voie';
      case 'YELLOW':
        return 'Attention';
      case 'RED':
        return 'Depasse';
    }
  }

  protected statusSeverity(
    status: EnvelopeStatus,
  ): 'success' | 'warn' | 'danger' {
    switch (status) {
      case 'GREEN':
        return 'success';
      case 'YELLOW':
        return 'warn';
      case 'RED':
        return 'danger';
    }
  }

  protected clampedPercent(envelope: EnvelopeResponse): number {
    return Math.min(100, Math.round(envelope.ratio * 100));
  }

  protected ariaFor(envelope: EnvelopeResponse): string {
    const pct = Math.round(envelope.ratio * 100);
    const descriptor =
      envelope.status === 'GREEN'
        ? 'sur la bonne voie'
        : envelope.status === 'YELLOW'
          ? 'attention'
          : 'depassee';
    return `Enveloppe ${envelope.name}: ${descriptor}, ${pct}% consomme`;
  }

  protected historyLabel(name: string): string {
    return `Voir l'historique de ${name}`;
  }

  protected formatAmount(amount: number): string {
    return new Intl.NumberFormat('fr-FR', {
      style: 'currency',
      currency: 'EUR',
    }).format(amount);
  }

  protected categoriesToShow(
    envelope: EnvelopeResponse,
  ): { id: string; name: string }[] {
    return envelope.categories.slice(0, 3);
  }

  protected categoryTooltip(envelope: EnvelopeResponse): string {
    return envelope.categories.map((c) => c.name).join(', ');
  }

  // Expose Math to template (not strictly needed — template uses clampedPercent)
  protected readonly Math = Math;

  // Track which accounts are archived/no-write for dialog pre-select
  protected currentAccount(accountId: string): AccountResponse | undefined {
    return this.accounts().find((a) => a.id === accountId);
  }
}
