import {
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
  inject,
  signal,
} from '@angular/core';
import { DatePipe } from '@angular/common';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute } from '@angular/router';
import { TableModule } from 'primeng/table';
import { ButtonModule } from 'primeng/button';
import { TagModule } from 'primeng/tag';
import { ConfirmDialogModule } from 'primeng/confirmdialog';
import { MessageModule } from 'primeng/message';
import { TooltipModule } from 'primeng/tooltip';
import { InputNumberModule } from 'primeng/inputnumber';
import { DatePickerModule } from 'primeng/datepicker';
import { InputTextModule } from 'primeng/inputtext';
import { FloatLabelModule } from 'primeng/floatlabel';
import { ConfirmationService, TreeNode } from 'primeng/api';
import { TreeSelectModule } from 'primeng/treeselect';
import { TransactionService } from './transaction.service';
import { TransactionResponse, TransactionFilters } from './transaction.types';
import { TransactionDialog } from './transaction-dialog';
import { AccountService } from '../accounts/account.service';
import { CategoryService } from '../categories/category.service';

@Component({
  selector: 'app-transactions',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    DatePipe,
    FormsModule,
    TableModule,
    ButtonModule,
    TagModule,
    ConfirmDialogModule,
    MessageModule,
    TooltipModule,
    InputNumberModule,
    DatePickerModule,
    InputTextModule,
    FloatLabelModule,
    TreeSelectModule,
    TransactionDialog,
  ],
  providers: [ConfirmationService],
  template: `
    <div class="p-8">
      <!-- Header -->
      <div class="flex items-center justify-between mb-6">
        <h1 class="text-2xl font-semibold leading-tight">Transactions &mdash; {{ accountName() }}</h1>
        <p-button label="Ajouter une transaction" icon="pi pi-plus" (onClick)="openCreateDialog()" />
      </div>

      <!-- Error -->
      @if (error()) {
        <p-message severity="error" [text]="error()!" styleClass="mb-4 w-full" />
      }

      <!-- Filter bar -->
      <div class="bg-surface-50 rounded-lg p-4 mb-4" role="search" aria-label="Filtrer les transactions">
        <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
          <p-floatlabel variant="on">
            <p-datepicker [(ngModel)]="filterDateFrom" dateFormat="dd/mm/yy" [showIcon]="true" inputId="dateFrom" />
            <label for="dateFrom">Du</label>
          </p-floatlabel>
          <p-floatlabel variant="on">
            <p-datepicker [(ngModel)]="filterDateTo" dateFormat="dd/mm/yy" [showIcon]="true" inputId="dateTo" />
            <label for="dateTo">Au</label>
          </p-floatlabel>
          <p-floatlabel variant="on">
            <p-inputnumber [(ngModel)]="filterAmountMin" mode="decimal" [minFractionDigits]="2" inputId="amountMin" />
            <label for="amountMin">Montant min</label>
          </p-floatlabel>
          <p-floatlabel variant="on">
            <p-inputnumber [(ngModel)]="filterAmountMax" mode="decimal" [minFractionDigits]="2" inputId="amountMax" />
            <label for="amountMax">Montant max</label>
          </p-floatlabel>
          <p-treeselect
            [options]="categoryOptions()"
            [(ngModel)]="filterCategoryNode"
            [filter]="true"
            [showClear]="true"
            selectionMode="single"
            placeholder="Categorie"
            appendTo="body"
            (onNodeSelect)="onFilterCategorySelect($event)"
            (onClear)="onFilterCategoryClear()"
            styleClass="w-full"
          />
          <p-floatlabel variant="on">
            <input pInputText [(ngModel)]="filterSearch" id="search" />
            <label for="search">Recherche</label>
          </p-floatlabel>
        </div>
        <div class="flex gap-2 mt-4 justify-end">
          <p-button label="Reinitialiser" severity="secondary" [text]="true" (onClick)="resetFilters()" />
          <p-button label="Filtrer" icon="pi pi-search" (onClick)="applyFilters()" />
        </div>
      </div>

      <!-- Empty state -->
      @if (!loading() && transactions().length === 0 && totalRecords() === 0) {
        <div role="status" class="text-center py-12">
          <h2 class="text-lg font-semibold mb-2">Aucune transaction</h2>
          <p class="text-muted-color mb-4">Ajoutez votre premiere transaction pour commencer a suivre les mouvements de ce compte.</p>
          <p-button label="Ajouter une transaction" icon="pi pi-plus" (onClick)="openCreateDialog()" />
        </div>
      }

      <!-- Table -->
      @if (totalRecords() > 0 || loading()) {
        <p-table
          [value]="transactions()"
          [lazy]="true"
          [paginator]="true"
          [rows]="pageSize"
          [totalRecords]="totalRecords()"
          [loading]="loading()"
          (onLazyLoad)="loadTransactions($event)"
          [sortField]="'transactionDate'"
          [sortOrder]="-1"
          [stripedRows]="true"
          [rowsPerPageOptions]="[10, 20, 50]"
          styleClass="p-datatable-sm"
        >
          <ng-template pTemplate="header">
            <tr>
              <th scope="col">Date</th>
              <th scope="col">Description</th>
              <th scope="col">Categorie</th>
              <th scope="col" class="text-right">Montant</th>
              <th scope="col" class="text-center">Pointe</th>
              <th scope="col">Actions</th>
            </tr>
          </ng-template>
          <ng-template pTemplate="body" let-tx>
            <tr>
              <td>{{ tx.transactionDate | date:'dd/MM/yyyy' }}</td>
              <td>
                {{ tx.description ?? '—' }}
                @if (tx.source === 'RECURRING') {
                  <p-tag value="Recurrent" severity="info" styleClass="ml-2" />
                }
              </td>
              <td>{{ tx.categoryName ?? '—' }}</td>
              <td
                class="text-right tabular-nums"
                [class.text-green-500]="tx.amount > 0"
                [class.text-red-500]="tx.amount < 0"
              >
                {{ formatAmount(tx.amount) }}
              </td>
              <td class="text-center">
                <button
                  class="p-link"
                  (click)="togglePointed(tx)"
                  [attr.aria-label]="tx.pointed ? 'Depointer la transaction' : 'Pointer la transaction'"
                >
                  @if (tx.pointed) {
                    <i class="pi pi-check text-primary"></i>
                  }
                </button>
              </td>
              <td>
                @if (tx.source === 'MANUAL') {
                  <div class="flex gap-1">
                    <p-button
                      icon="pi pi-pencil"
                      severity="secondary"
                      [text]="true"
                      [rounded]="true"
                      pTooltip="Modifier la transaction"
                      (onClick)="openEditDialog(tx)"
                    />
                    <p-button
                      icon="pi pi-trash"
                      severity="danger"
                      [text]="true"
                      [rounded]="true"
                      pTooltip="Supprimer la transaction"
                      (onClick)="confirmDelete(tx)"
                    />
                  </div>
                }
              </td>
            </tr>
          </ng-template>
          <ng-template pTemplate="summary">
            <span>{{ totalRecords() }} transactions</span>
          </ng-template>
        </p-table>
      }

      <p-confirmdialog />

      @if (showDialog()) {
        <app-transaction-dialog
          [accountId]="accountId()"
          [transaction]="editingTransaction()"
          [categoryOptions]="categoryOptions()"
          (saved)="onDialogSaved()"
          (cancelled)="showDialog.set(false)"
        />
      }
    </div>
  `,
})
export class Transactions {
  private readonly route = inject(ActivatedRoute);
  private readonly transactionService = inject(TransactionService);
  private readonly accountService = inject(AccountService);
  private readonly categoryService = inject(CategoryService);
  private readonly confirmationService = inject(ConfirmationService);
  private readonly destroyRef = inject(DestroyRef);

  protected accountId = signal<string>('');
  protected accountName = signal<string>('');
  protected transactions = signal<TransactionResponse[]>([]);
  protected totalRecords = signal<number>(0);
  protected loading = signal<boolean>(true);
  protected error = signal<string | null>(null);
  protected readonly pageSize = 20;

  // Filter state (plain properties for ngModel two-way binding)
  protected filterDateFrom: Date | null = null;
  protected filterDateTo: Date | null = null;
  protected filterAmountMin: number | null = null;
  protected filterAmountMax: number | null = null;
  protected filterCategoryId: string | null = null;
  protected filterCategoryNode: TreeNode | null = null;
  protected filterSearch: string = '';

  // Category options for the tree select
  protected categoryOptions = signal<TreeNode[]>([]);

  // Dialog state
  protected showDialog = signal<boolean>(false);
  protected editingTransaction = signal<TransactionResponse | null>(null);

  // Track current page for reload
  private currentPage = 0;

  constructor() {
    this.route.params.pipe(takeUntilDestroyed(this.destroyRef)).subscribe((params) => {
      this.accountId.set(params['accountId'] as string);
      this.loadAccountName();
    });

    this.categoryService
      .loadCategories()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe((cats) => {
        const roots = cats.filter((c) => !c.parentId);
        const nodes: TreeNode[] = roots.map((root) => {
          const children = cats.filter((c) => c.parentId === root.id);
          return {
            label: root.name,
            data: root.id,
            children:
              children.length > 0
                ? children.map((child) => ({ label: child.name, data: child.id }))
                : undefined,
          };
        });
        this.categoryOptions.set(nodes);
      });
  }

  private loadAccountName(): void {
    const accounts = this.accountService.accounts();
    const found = accounts.find((a) => a.id === this.accountId());
    if (found) {
      this.accountName.set(found.name);
    } else {
      this.accountService
        .loadAccounts()
        .pipe(takeUntilDestroyed(this.destroyRef))
        .subscribe((accts) => {
          const account = accts.find((a) => a.id === this.accountId());
          if (account) this.accountName.set(account.name);
        });
    }
  }

  protected loadTransactions(event: { first?: number | null; rows?: number | null }): void {
    const first = event.first ?? 0;
    const rows = event.rows ?? this.pageSize;
    const page = Math.floor(first / rows);
    this.currentPage = page;

    const filters: TransactionFilters = {};
    if (this.filterDateFrom) {
      filters.dateFrom = this.toDateString(this.filterDateFrom);
    }
    if (this.filterDateTo) {
      filters.dateTo = this.toDateString(this.filterDateTo);
    }
    if (this.filterAmountMin != null) filters.amountMin = this.filterAmountMin;
    if (this.filterAmountMax != null) filters.amountMax = this.filterAmountMax;
    if (this.filterCategoryId) filters.categoryId = this.filterCategoryId;
    if (this.filterSearch) filters.search = this.filterSearch;

    this.loading.set(true);
    this.error.set(null);

    this.transactionService
      .getTransactions(this.accountId(), page, rows, filters)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (pageResult) => {
          this.transactions.set(pageResult.content);
          this.totalRecords.set(pageResult.totalElements);
          this.loading.set(false);
        },
        error: () => {
          this.loading.set(false);
          this.error.set(
            'Impossible de charger les transactions. Verifiez votre connexion et reessayez.',
          );
        },
      });
  }

  protected applyFilters(): void {
    this.loadTransactions({ first: 0, rows: this.pageSize });
  }

  protected resetFilters(): void {
    this.filterDateFrom = null;
    this.filterDateTo = null;
    this.filterAmountMin = null;
    this.filterAmountMax = null;
    this.filterCategoryId = null;
    this.filterCategoryNode = null;
    this.filterSearch = '';
    this.loadTransactions({ first: 0, rows: this.pageSize });
  }

  protected onFilterCategorySelect(event: { node: TreeNode }): void {
    this.filterCategoryId = event.node.data as string;
  }

  protected onFilterCategoryClear(): void {
    this.filterCategoryId = null;
  }

  protected openCreateDialog(): void {
    this.editingTransaction.set(null);
    this.showDialog.set(true);
  }

  protected openEditDialog(tx: TransactionResponse): void {
    this.editingTransaction.set(tx);
    this.showDialog.set(true);
  }

  protected onDialogSaved(): void {
    this.showDialog.set(false);
    this.loadTransactions({ first: this.currentPage * this.pageSize, rows: this.pageSize });
  }

  protected confirmDelete(tx: TransactionResponse): void {
    const amountFormatted = this.formatAmount(tx.amount);
    this.confirmationService.confirm({
      header: 'Supprimer la transaction',
      message: `Etes-vous sur de vouloir supprimer cette transaction de ${amountFormatted} du ${tx.transactionDate} ? Cette action est irreversible.`,
      acceptLabel: 'Supprimer',
      rejectLabel: 'Annuler',
      accept: () => {
        this.transactionService
          .deleteTransaction(tx.id)
          .pipe(takeUntilDestroyed(this.destroyRef))
          .subscribe({
            next: () =>
              this.loadTransactions({ first: this.currentPage * this.pageSize, rows: this.pageSize }),
            error: () =>
              this.error.set('Impossible de supprimer la transaction. Veuillez reessayer.'),
          });
      },
    });
  }

  protected togglePointed(tx: TransactionResponse): void {
    this.transactionService
      .togglePointed(tx.id)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (updated) => {
          this.transactions.update((list) => list.map((t) => (t.id === updated.id ? updated : t)));
        },
        error: () => {
          this.error.set('Impossible de modifier le pointage. Veuillez reessayer.');
        },
      });
  }

  protected formatAmount(amount: number): string {
    return new Intl.NumberFormat('fr-FR', { style: 'currency', currency: 'EUR' }).format(amount);
  }

  private toDateString(date: Date): string {
    const y = date.getFullYear();
    const m = String(date.getMonth() + 1).padStart(2, '0');
    const d = String(date.getDate()).padStart(2, '0');
    return `${y}-${m}-${d}`;
  }
}
