import {
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
  computed,
  inject,
  signal,
} from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { DatePipe } from '@angular/common';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { TreeNode, ConfirmationService } from 'primeng/api';
import { TableModule } from 'primeng/table';
import { TagModule } from 'primeng/tag';
import { ProgressBarModule } from 'primeng/progressbar';
import { ButtonModule } from 'primeng/button';
import { MessageModule } from 'primeng/message';
import { TooltipModule } from 'primeng/tooltip';
import { ConfirmDialogModule } from 'primeng/confirmdialog';
import { EnvelopeService } from './envelope.service';
import {
  EnvelopeHistoryEntry,
  EnvelopeResponse,
  EnvelopeStatus,
} from './envelope.types';
import { AccountService } from '../accounts/account.service';
import { CategoryService } from '../categories/category.service';
import { EnvelopeDialog } from './envelope-dialog';
import { EnvelopeAllocationDialog } from './envelope-allocation-dialog';

@Component({
  selector: 'app-envelope-details',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    RouterLink,
    TableModule,
    TagModule,
    ProgressBarModule,
    ButtonModule,
    MessageModule,
    TooltipModule,
    ConfirmDialogModule,
    EnvelopeDialog,
    EnvelopeAllocationDialog,
  ],
  providers: [ConfirmationService, DatePipe],
  template: `
    <div class="p-8">
      @if (error()) {
        <p-message severity="error" [text]="error()!" styleClass="mb-4 w-full" />
      }

      @if (envelope(); as env) {
        <!-- Header -->
        <div class="flex items-start justify-between mb-6">
          <div>
            <a
              class="flex items-center gap-2 text-muted-color hover:text-primary mb-2"
              [routerLink]="['/envelopes']"
            >
              <i class="pi pi-arrow-left" aria-hidden="true"></i>
              <span>Retour aux enveloppes</span>
            </a>
            <h1 class="text-2xl font-semibold leading-tight">{{ env.name }}</h1>
            <p class="text-sm text-muted-color">
              {{ env.bankAccountName }} &middot; {{ scopeLabel(env.scope) }}
            </p>
          </div>
          <div class="flex items-center gap-2">
            <p-tag
              [value]="statusLabel(env.status)"
              [severity]="statusSeverity(env.status)"
            />
            @if (hasWriteAccess(env.bankAccountId)) {
              <p-button
                label="Personnaliser ce mois"
                icon="pi pi-calendar-plus"
                severity="secondary"
                [outlined]="true"
                (onClick)="openAllocationDialog()"
              />
              <p-button
                label="Modifier"
                icon="pi pi-pencil"
                (onClick)="openEditDialog()"
              />
              <p-button
                icon="pi pi-trash"
                severity="danger"
                [text]="true"
                pTooltip="Archiver l'enveloppe"
                (onClick)="confirmArchive()"
                [attr.aria-label]="'Archiver ' + env.name"
              />
            }
          </div>
        </div>

        <!-- Summary card -->
        <div class="bg-surface-50 rounded-lg p-4 mb-6">
          <div class="grid grid-cols-3 gap-4 text-center">
            <div>
              <p class="text-sm text-muted-color">Budget effectif</p>
              <p class="text-2xl font-semibold tabular-nums">
                {{ formatAmount(env.effectiveBudget) }}
              </p>
            </div>
            <div>
              <p class="text-sm text-muted-color">Consomme</p>
              <p class="text-2xl font-semibold tabular-nums">
                {{ formatAmount(env.consumed) }}
              </p>
            </div>
            <div>
              <p class="text-sm text-muted-color">Restant</p>
              <p
                class="text-2xl font-semibold tabular-nums"
                [class.text-red-500]="env.available < 0"
              >
                {{ formatAmount(env.available) }}
              </p>
            </div>
          </div>
          <p-progressbar
            [value]="clampedPercent(env)"
            [attr.aria-label]="ariaFor(env)"
            styleClass="h-2 mt-4"
          />
        </div>

        <!-- History -->
        <h2 class="text-lg font-semibold mb-2">Historique (12 derniers mois)</h2>

        @if (isHistoryEmpty()) {
          <div role="status" class="text-center py-12">
            <h2 class="text-lg font-semibold mb-2">Pas encore d'historique</h2>
            <p class="text-muted-color mb-4">
              L'historique apparaitra des qu'une transaction sera imputee a cette enveloppe.
            </p>
            <p-button
              label="Voir les transactions du compte"
              severity="secondary"
              [outlined]="true"
              [routerLink]="['/accounts', env.bankAccountId, 'transactions']"
            />
          </div>
        } @else {
          <p-table
            [value]="history()"
            [stripedRows]="true"
            sortField="month"
            [sortOrder]="-1"
            styleClass="p-datatable-sm"
          >
            <ng-template pTemplate="header">
              <tr>
                <th pSortableColumn="month" scope="col">
                  Mois <p-sortIcon field="month" />
                </th>
                <th scope="col" class="text-right">Budget effectif</th>
                <th scope="col" class="text-right">Consomme</th>
                <th scope="col" class="text-right">Restant</th>
                <th scope="col">Statut</th>
                <th scope="col">Actions</th>
              </tr>
            </ng-template>
            <ng-template pTemplate="body" let-row>
              <tr>
                <td>{{ formatMonth(row.month) }}</td>
                <td class="text-right tabular-nums">
                  {{ formatAmount(row.effectiveBudget) }}
                </td>
                <td class="text-right tabular-nums">
                  {{ formatAmount(row.consumed) }}
                </td>
                <td
                  class="text-right tabular-nums"
                  [class.text-red-500]="row.available < 0"
                >
                  {{ formatAmount(row.available) }}
                </td>
                <td>
                  <div class="flex items-center gap-2">
                    <p-tag
                      [value]="statusLabel(row.status)"
                      [severity]="statusSeverity(row.status)"
                    />
                    <p-progressbar
                      [value]="clampedPercent(row)"
                      [attr.aria-label]="ariaForHistory(row)"
                      styleClass="h-2 w-24"
                    />
                  </div>
                </td>
                <td>
                  <p-button
                    icon="pi pi-external-link"
                    [text]="true"
                    [rounded]="true"
                    severity="secondary"
                    pTooltip="Voir les transactions du mois"
                    (onClick)="openMonthTransactions(env, row)"
                    [attr.aria-label]="'Voir les transactions de ' + formatMonth(row.month)"
                  />
                </td>
              </tr>
            </ng-template>
          </p-table>
        }

        <p-confirmdialog />

        @if (showEditDialog()) {
          <app-envelope-dialog
            [visible]="true"
            mode="edit"
            [envelope]="env"
            [accounts]="accounts()"
            [categoryOptions]="categoryOptions()"
            [lockedAccountId]="env.bankAccountId"
            (saved)="onDialogSaved()"
            (cancelled)="showEditDialog.set(false)"
          />
        }

        @if (showAllocationDialog()) {
          <app-envelope-allocation-dialog
            [visible]="true"
            [envelope]="env"
            (saved)="onAllocationSaved()"
            (cancelled)="showAllocationDialog.set(false)"
          />
        }
      }
    </div>
  `,
})
export class EnvelopeDetailsPage {
  private readonly envelopeService = inject(EnvelopeService);
  private readonly accountService = inject(AccountService);
  private readonly categoryService = inject(CategoryService);
  private readonly confirmationService = inject(ConfirmationService);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly destroyRef = inject(DestroyRef);

  protected readonly envelope = signal<EnvelopeResponse | null>(null);
  protected readonly history = signal<EnvelopeHistoryEntry[]>([]);
  protected readonly error = signal<string | null>(null);
  protected readonly categoryOptions = signal<TreeNode[]>([]);
  protected readonly accounts = this.accountService.accounts;

  protected readonly showEditDialog = signal<boolean>(false);
  protected readonly showAllocationDialog = signal<boolean>(false);

  protected readonly isHistoryEmpty = computed(() => {
    const list = this.history();
    return list.length === 0 || list.every((entry) => entry.consumed === 0);
  });

  constructor() {
    // Load accounts and categories for dialogs.
    this.accountService
      .loadAccounts()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe();

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

    this.route.paramMap
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe((params) => {
        const id = params.get('id');
        if (id) this.loadDetails(id);
      });
  }

  private loadDetails(id: string): void {
    this.envelopeService
      .getEnvelope(id)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (env) => this.envelope.set(env),
        error: () =>
          this.error.set(
            "Impossible de charger l'enveloppe. Verifiez votre connexion et reessayez.",
          ),
      });

    this.envelopeService
      .getHistory(id)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (list) => this.history.set(list),
        error: () => this.history.set([]),
      });
  }

  protected openEditDialog(): void {
    this.showEditDialog.set(true);
  }

  protected openAllocationDialog(): void {
    this.showAllocationDialog.set(true);
  }

  protected onDialogSaved(): void {
    this.showEditDialog.set(false);
    const env = this.envelope();
    if (env) this.loadDetails(env.id);
  }

  protected onAllocationSaved(): void {
    this.showAllocationDialog.set(false);
    const env = this.envelope();
    if (env) this.loadDetails(env.id);
  }

  protected confirmArchive(): void {
    const env = this.envelope();
    if (!env) return;
    this.confirmationService.confirm({
      header: "Archiver l'enveloppe",
      message: `Etes-vous sur de vouloir archiver l'enveloppe "${env.name}" ? Son historique reste consultable dans les archives mais elle ne sera plus affichee par defaut.`,
      acceptLabel: 'Archiver',
      rejectLabel: 'Annuler',
      acceptButtonProps: { severity: 'danger' },
      accept: () => {
        this.envelopeService
          .deleteEnvelope(env.id)
          .pipe(takeUntilDestroyed(this.destroyRef))
          .subscribe({
            next: () => this.router.navigate(['/envelopes']),
            error: () =>
              this.error.set(
                "Impossible d'archiver l'enveloppe. Veuillez reessayer.",
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

  protected openMonthTransactions(
    env: EnvelopeResponse,
    entry: EnvelopeHistoryEntry,
  ): void {
    const { dateFrom, dateTo } = this.monthBounds(entry.month);
    const categoryIds = env.categories.map((c) => c.id).join(',');
    this.router.navigate(['/accounts', env.bankAccountId, 'transactions'], {
      queryParams: {
        dateFrom,
        dateTo,
        categoryIds,
      },
    });
  }

  private monthBounds(month: string): { dateFrom: string; dateTo: string } {
    const parts = month.split('-');
    const y = parseInt(parts[0], 10);
    const m = parseInt(parts[1], 10);
    const firstDay = new Date(y, m - 1, 1);
    const lastDay = new Date(y, m, 0);
    return {
      dateFrom: this.toDateString(firstDay),
      dateTo: this.toDateString(lastDay),
    };
  }

  private toDateString(d: Date): string {
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, '0');
    const day = String(d.getDate()).padStart(2, '0');
    return `${y}-${m}-${day}`;
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

  protected scopeLabel(scope: 'PERSONAL' | 'SHARED'): string {
    return scope === 'SHARED' ? 'Commun' : 'Personnel';
  }

  protected clampedPercent(
    envelope: EnvelopeResponse | EnvelopeHistoryEntry,
  ): number {
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

  protected ariaForHistory(entry: EnvelopeHistoryEntry): string {
    const pct = Math.round(entry.ratio * 100);
    return `${this.formatMonth(entry.month)}: ${pct}% consomme`;
  }

  protected formatAmount(amount: number): string {
    return new Intl.NumberFormat('fr-FR', {
      style: 'currency',
      currency: 'EUR',
    }).format(amount);
  }

  protected formatMonth(iso: string): string {
    const parts = iso.split('-');
    const y = parseInt(parts[0], 10);
    const m = parseInt(parts[1], 10) - 1;
    const d = new Date(y, m, 1);
    return new Intl.DateTimeFormat('fr-FR', {
      month: 'long',
      year: 'numeric',
    }).format(d);
  }
}
