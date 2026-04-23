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
import { HttpErrorResponse } from '@angular/common/http';
import { DialogModule } from 'primeng/dialog';
import { DatePickerModule } from 'primeng/datepicker';
import { InputNumberModule } from 'primeng/inputnumber';
import { FloatLabelModule } from 'primeng/floatlabel';
import { ButtonModule } from 'primeng/button';
import { TableModule } from 'primeng/table';
import { MessageModule } from 'primeng/message';
import { TooltipModule } from 'primeng/tooltip';
import { ConfirmDialogModule } from 'primeng/confirmdialog';
import { ConfirmationService } from 'primeng/api';
import { EnvelopeService } from './envelope.service';
import {
  EnvelopeAllocationResponse,
  EnvelopeResponse,
} from './envelope.types';

@Component({
  selector: 'app-envelope-allocation-dialog',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    FormsModule,
    DialogModule,
    DatePickerModule,
    InputNumberModule,
    FloatLabelModule,
    ButtonModule,
    TableModule,
    MessageModule,
    TooltipModule,
    ConfirmDialogModule,
  ],
  providers: [ConfirmationService],
  template: `
    <p-dialog
      header="Personnaliser le budget d'un mois"
      [visible]="visible()"
      [modal]="true"
      [closable]="true"
      [draggable]="false"
      [style]="{ width: '36rem' }"
      (onHide)="cancelled.emit()"
      (visibleChange)="!$event && cancelled.emit()"
    >
      <div class="flex flex-col gap-4 p-6">
        @if (envelope(); as env) {
          <p class="text-sm text-muted-color">{{ env.name }}</p>
        }

        <!-- Month -->
        <p-floatlabel variant="on">
          <p-datepicker
            inputId="overrideMonth"
            [ngModel]="month()"
            (ngModelChange)="month.set($event)"
            view="month"
            dateFormat="mm/yy"
            [showIcon]="true"
          />
          <label for="overrideMonth">Mois concerne</label>
        </p-floatlabel>

        <!-- Amount -->
        <p-floatlabel variant="on">
          <p-inputnumber
            inputId="overrideAmount"
            [ngModel]="allocatedAmount()"
            (ngModelChange)="allocatedAmount.set($event)"
            mode="currency"
            currency="EUR"
            locale="fr-FR"
            [minFractionDigits]="2"
            [min]="0"
          />
          <label for="overrideAmount">Budget pour ce mois</label>
        </p-floatlabel>

        <p-message
          severity="info"
          text="Ce montant remplace le budget par defaut pour le mois choisi uniquement."
          styleClass="w-full"
        />

        @if (error()) {
          <p-message severity="error" [text]="error()!" />
        }

        <div>
          <h3 class="text-sm font-semibold mb-2">Personnalisations existantes</h3>
          @if (existingAllocations().length === 0) {
            <p class="text-sm text-muted-color py-4 text-center">
              Aucune personnalisation pour le moment.
            </p>
          } @else {
            <p-table
              [value]="existingAllocations()"
              styleClass="p-datatable-sm"
              sortField="month"
              [sortOrder]="1"
            >
              <ng-template pTemplate="header">
                <tr>
                  <th scope="col">Mois</th>
                  <th scope="col" class="text-right">Budget</th>
                  <th scope="col">Actions</th>
                </tr>
              </ng-template>
              <ng-template pTemplate="body" let-allocation>
                <tr>
                  <td>{{ formatMonth(allocation.month) }}</td>
                  <td class="text-right tabular-nums">
                    {{ formatAmount(allocation.allocatedAmount) }}
                  </td>
                  <td>
                    <p-button
                      icon="pi pi-pencil"
                      [text]="true"
                      [rounded]="true"
                      severity="secondary"
                      pTooltip="Modifier"
                      (onClick)="loadIntoForm(allocation)"
                      [attr.aria-label]="'Modifier la personnalisation de ' + formatMonth(allocation.month)"
                    />
                    <p-button
                      icon="pi pi-trash"
                      [text]="true"
                      [rounded]="true"
                      severity="danger"
                      pTooltip="Supprimer"
                      (onClick)="confirmDelete(allocation)"
                      [attr.aria-label]="'Supprimer la personnalisation de ' + formatMonth(allocation.month)"
                    />
                  </td>
                </tr>
              </ng-template>
            </p-table>
          }
        </div>
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
            [disabled]="!isValid() || submitting()"
            (onClick)="save()"
            data-testid="save-allocation-button"
          />
        </div>
      </ng-template>
    </p-dialog>

    <p-confirmdialog />
  `,
})
export class EnvelopeAllocationDialog {
  visible = input<boolean>(false);
  envelope = input<EnvelopeResponse | null>(null);

  saved = output<EnvelopeAllocationResponse>();
  cancelled = output<void>();
  allocationDeleted = output<void>();

  private readonly envelopeService = inject(EnvelopeService);
  private readonly confirmationService = inject(ConfirmationService);
  private readonly destroyRef = inject(DestroyRef);

  protected readonly month = signal<Date>(this.firstOfCurrentMonth());
  protected readonly allocatedAmount = signal<number | null>(null);

  protected readonly submitting = signal<boolean>(false);
  protected readonly error = signal<string | null>(null);
  protected readonly existingAllocations = signal<EnvelopeAllocationResponse[]>([]);

  /** Holds the current allocation being edited (if any), to know between create vs update. */
  protected readonly editingAllocation = signal<EnvelopeAllocationResponse | null>(null);

  protected readonly envelopeId = computed(() => this.envelope()?.id ?? null);

  protected readonly isValid = computed(() => {
    const amount = this.allocatedAmount();
    return amount !== null && amount >= 0;
  });

  constructor() {
    // Reset + reload whenever envelope input changes.
    effect(() => {
      const env = this.envelope();
      this.month.set(this.firstOfCurrentMonth());
      this.allocatedAmount.set(null);
      this.editingAllocation.set(null);
      this.error.set(null);
      if (env) {
        this.loadAllocations(env.id);
      } else {
        this.existingAllocations.set([]);
      }
    });
  }

  protected save(): void {
    if (!this.isValid()) return;

    const env = this.envelope();
    if (!env) return;

    this.submitting.set(true);
    this.error.set(null);

    const editing = this.editingAllocation();
    const request = {
      month: this.monthToIsoString(this.month()),
      allocatedAmount: this.allocatedAmount()!,
    };

    const obs$ = editing
      ? this.envelopeService.updateAllocation(editing.id, request)
      : this.envelopeService.createAllocation(env.id, request);

    obs$
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (resp) => {
          this.submitting.set(false);
          this.saved.emit(resp);
        },
        error: (err: HttpErrorResponse) => {
          this.submitting.set(false);
          if (err.status === 409) {
            this.error.set(
              'Un budget personnalise existe deja pour ce mois. Modifiez-le depuis la liste ci-dessous.',
            );
          } else if (err.status === 403) {
            this.error.set(
              "Vous n'avez pas les droits pour modifier les enveloppes de ce compte.",
            );
          } else {
            this.error.set(
              'Impossible d\'enregistrer la personnalisation mensuelle. Veuillez reessayer.',
            );
          }
        },
      });
  }

  protected loadIntoForm(allocation: EnvelopeAllocationResponse): void {
    this.editingAllocation.set(allocation);
    this.month.set(this.parseMonth(allocation.month));
    this.allocatedAmount.set(allocation.allocatedAmount);
  }

  protected confirmDelete(allocation: EnvelopeAllocationResponse): void {
    const label = this.formatMonth(allocation.month);
    this.confirmationService.confirm({
      header: 'Supprimer la personnalisation',
      message: `Supprimer le budget personnalise de ${label} ? Le budget par defaut sera applique a nouveau.`,
      acceptLabel: 'Supprimer',
      rejectLabel: 'Annuler',
      acceptButtonProps: { severity: 'danger' },
      accept: () => {
        this.envelopeService
          .deleteAllocation(allocation.id)
          .pipe(takeUntilDestroyed(this.destroyRef))
          .subscribe({
            next: () => {
              const env = this.envelope();
              if (env) this.loadAllocations(env.id);
              if (this.editingAllocation()?.id === allocation.id) {
                this.editingAllocation.set(null);
                this.allocatedAmount.set(null);
                this.month.set(this.firstOfCurrentMonth());
              }
              this.allocationDeleted.emit();
            },
            error: () =>
              this.error.set(
                'Impossible de supprimer la personnalisation. Veuillez reessayer.',
              ),
          });
      },
    });
  }

  private loadAllocations(envelopeId: string): void {
    this.envelopeService
      .listAllocations(envelopeId)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (list) => {
          // Sort by month ascending.
          const sorted = [...list].sort((a, b) => a.month.localeCompare(b.month));
          this.existingAllocations.set(sorted);
        },
        error: () => {
          this.existingAllocations.set([]);
        },
      });
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
    return new Intl.DateTimeFormat('fr-FR', { month: 'long', year: 'numeric' }).format(d);
  }

  private monthToIsoString(date: Date): string {
    const y = date.getFullYear();
    const m = String(date.getMonth() + 1).padStart(2, '0');
    return `${y}-${m}`;
  }

  private parseMonth(iso: string): Date {
    const parts = iso.split('-');
    return new Date(parseInt(parts[0], 10), parseInt(parts[1], 10) - 1, 1);
  }

  private firstOfCurrentMonth(): Date {
    const now = new Date();
    return new Date(now.getFullYear(), now.getMonth(), 1);
  }
}
