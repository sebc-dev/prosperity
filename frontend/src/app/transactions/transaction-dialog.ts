import {
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
  computed,
  effect,
  inject,
  input,
  output,
  signal,
} from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormsModule } from '@angular/forms';
import { DialogModule } from 'primeng/dialog';
import { FloatLabelModule } from 'primeng/floatlabel';
import { InputTextModule } from 'primeng/inputtext';
import { InputNumberModule } from 'primeng/inputnumber';
import { DatePickerModule } from 'primeng/datepicker';
import { ButtonModule } from 'primeng/button';
import { MessageModule } from 'primeng/message';
import { TreeNode } from 'primeng/api';
import { TreeSelectModule } from 'primeng/treeselect';
import { HttpErrorResponse } from '@angular/common/http';
import { TransactionService } from './transaction.service';
import { TransactionResponse } from './transaction.types';

@Component({
  selector: 'app-transaction-dialog',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    FormsModule,
    DialogModule,
    FloatLabelModule,
    InputTextModule,
    InputNumberModule,
    DatePickerModule,
    ButtonModule,
    MessageModule,
    TreeSelectModule,
  ],
  template: `
    <p-dialog
      [header]="dialogHeader()"
      [visible]="true"
      (onHide)="cancelled.emit()"
      [modal]="true"
      [closable]="true"
      [draggable]="false"
      [style]="{ width: '32rem' }"
    >
      <div class="flex flex-col gap-4 p-6">
        <p-floatlabel variant="on">
          <p-inputnumber
            [(ngModel)]="amount"
            mode="currency"
            currency="EUR"
            locale="fr-FR"
            [minFractionDigits]="2"
            inputId="amount"
          />
          <label for="amount">Montant (EUR)</label>
        </p-floatlabel>

        <p-floatlabel variant="on">
          <p-datepicker
            [(ngModel)]="transactionDate"
            dateFormat="dd/mm/yy"
            [showIcon]="true"
            inputId="transactionDate"
          />
          <label for="transactionDate">Date</label>
        </p-floatlabel>

        <p-floatlabel variant="on">
          <input
            pInputText
            [(ngModel)]="description"
            id="description"
            class="w-full"
            maxlength="500"
          />
          <label for="description">Description</label>
        </p-floatlabel>

        <p-treeselect
          [options]="categoryOptions()"
          [(ngModel)]="selectedCategoryNode"
          [filter]="true"
          [showClear]="true"
          selectionMode="single"
          placeholder="Categorie"
          appendTo="body"
          (onNodeSelect)="onCategorySelect($event)"
          (onClear)="onCategoryClear()"
          styleClass="w-full"
        />

        @if (error()) {
          <p-message severity="error" [text]="error()!" />
        }
      </div>

      <ng-template pTemplate="footer">
        <div class="flex justify-end gap-2">
          <p-button
            label="Annuler"
            [text]="true"
            severity="secondary"
            (onClick)="cancelled.emit()"
          />
          <p-button
            [label]="submitting() ? 'Enregistrement...' : 'Enregistrer'"
            [loading]="submitting()"
            [disabled]="!isValid || submitting()"
            (onClick)="save()"
          />
        </div>
      </ng-template>
    </p-dialog>
  `,
})
export class TransactionDialog {
  accountId = input.required<string>();
  transaction = input<TransactionResponse | null>(null);
  categoryOptions = input<TreeNode[]>([]);

  saved = output<void>();
  cancelled = output<void>();

  private readonly transactionService = inject(TransactionService);
  private readonly destroyRef = inject(DestroyRef);

  protected amount: number | null = null;
  protected transactionDate: Date | null = new Date();
  protected description: string = '';
  protected categoryId: string | null = null;
  protected selectedCategoryNode: TreeNode | null = null;

  protected submitting = signal<boolean>(false);
  protected error = signal<string | null>(null);

  protected isEdit = computed(() => this.transaction() !== null);
  protected dialogHeader = computed(() =>
    this.isEdit() ? 'Modifier la transaction' : 'Ajouter une transaction',
  );

  protected get isValid(): boolean {
    return this.amount !== null && this.amount !== 0 && this.transactionDate !== null;
  }

  constructor() {
    effect(() => {
      const tx = this.transaction();
      if (tx) {
        this.amount = tx.amount;
        const parts = tx.transactionDate.split('-');
        this.transactionDate = new Date(
          parseInt(parts[0]),
          parseInt(parts[1]) - 1,
          parseInt(parts[2]),
        );
        this.description = tx.description ?? '';
        this.categoryId = tx.categoryId;
        // Pre-select category node from options
        this.selectedCategoryNode = this.findNodeById(this.categoryOptions(), tx.categoryId);
      } else {
        this.amount = null;
        this.transactionDate = new Date();
        this.description = '';
        this.categoryId = null;
        this.selectedCategoryNode = null;
      }
      this.error.set(null);
    });
  }

  protected onCategorySelect(event: { node: TreeNode }): void {
    this.categoryId = event.node.data as string;
  }

  protected onCategoryClear(): void {
    this.categoryId = null;
    this.selectedCategoryNode = null;
  }

  protected save(): void {
    if (!this.isValid) return;

    this.submitting.set(true);
    this.error.set(null);

    const dateStr = this.toDateString(this.transactionDate!);
    const tx = this.transaction();

    if (tx) {
      const request: { amount?: number; transactionDate?: string; description?: string; categoryId?: string; clearCategory?: boolean } = {
        amount: this.amount!,
        transactionDate: dateStr,
        description: this.description || undefined,
      };
      if (this.categoryId) {
        request.categoryId = this.categoryId;
      } else {
        request.clearCategory = true;
      }

      this.transactionService
        .updateTransaction(tx.id, request)
        .pipe(takeUntilDestroyed(this.destroyRef))
        .subscribe({
          next: () => {
            this.submitting.set(false);
            this.saved.emit();
          },
          error: (err: HttpErrorResponse) => {
            this.submitting.set(false);
            if (err.status === 403) {
              this.error.set("Vous n'avez pas les droits pour cette operation.");
            } else {
              this.error.set("Impossible d'enregistrer la transaction. Veuillez reessayer.");
            }
          },
        });
    } else {
      const request: { amount: number; transactionDate: string; description?: string; categoryId?: string } = {
        amount: this.amount!,
        transactionDate: dateStr,
      };
      if (this.description) request.description = this.description;
      if (this.categoryId) request.categoryId = this.categoryId;

      this.transactionService
        .createTransaction(this.accountId(), request)
        .pipe(takeUntilDestroyed(this.destroyRef))
        .subscribe({
          next: () => {
            this.submitting.set(false);
            this.saved.emit();
          },
          error: (err: HttpErrorResponse) => {
            this.submitting.set(false);
            if (err.status === 403) {
              this.error.set("Vous n'avez pas les droits pour cette operation.");
            } else {
              this.error.set("Impossible d'enregistrer la transaction. Veuillez reessayer.");
            }
          },
        });
    }
  }

  private toDateString(date: Date): string {
    const y = date.getFullYear();
    const m = String(date.getMonth() + 1).padStart(2, '0');
    const d = String(date.getDate()).padStart(2, '0');
    return `${y}-${m}-${d}`;
  }

  private findNodeById(nodes: TreeNode[], id: string | null): TreeNode | null {
    if (!id) return null;
    for (const node of nodes) {
      if (node.data === id) return node;
      if (node.children) {
        const found = this.findNodeById(node.children, id);
        if (found) return found;
      }
    }
    return null;
  }
}
