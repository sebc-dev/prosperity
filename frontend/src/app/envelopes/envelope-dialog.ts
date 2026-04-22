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
import { FloatLabelModule } from 'primeng/floatlabel';
import { InputTextModule } from 'primeng/inputtext';
import { InputNumberModule } from 'primeng/inputnumber';
import { SelectModule } from 'primeng/select';
import { SelectButtonModule } from 'primeng/selectbutton';
import { ButtonModule } from 'primeng/button';
import { MessageModule } from 'primeng/message';
import { TagModule } from 'primeng/tag';
import { TreeNode } from 'primeng/api';
import { CategorySelector } from '../shared/category-selector';
import { AccountResponse } from '../accounts/account.types';
import { EnvelopeService } from './envelope.service';
import {
  EnvelopeResponse,
  RolloverPolicy,
} from './envelope.types';

type DialogMode = 'create' | 'edit';

@Component({
  selector: 'app-envelope-dialog',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    FormsModule,
    DialogModule,
    FloatLabelModule,
    InputTextModule,
    InputNumberModule,
    SelectModule,
    SelectButtonModule,
    ButtonModule,
    MessageModule,
    TagModule,
    CategorySelector,
  ],
  template: `
    <p-dialog
      [header]="header()"
      [visible]="visible()"
      [modal]="true"
      [closable]="true"
      [draggable]="false"
      [style]="{ width: '36rem' }"
      (onHide)="cancelled.emit()"
    >
      <div class="flex flex-col gap-4 p-6">
        <!-- Compte -->
        <div>
          <p-floatlabel variant="on">
            <p-select
              inputId="accountSelect"
              [options]="accounts()"
              [(ngModel)]="selectedAccountId"
              optionLabel="name"
              optionValue="id"
              [disabled]="mode() === 'edit' || lockedAccountId() !== null"
              appendTo="body"
              styleClass="w-full"
            />
            <label for="accountSelect">Compte</label>
          </p-floatlabel>
          @if (selectedAccount(); as account) {
            <div class="mt-2">
              @if (account.accountType === 'SHARED') {
                <p-tag
                  value="Commun"
                  severity="info"
                  pTooltip="Cette enveloppe sera partagee avec tous les utilisateurs ayant acces au compte commun."
                />
              } @else {
                <p-tag value="Personnel" severity="secondary" />
              }
            </div>
          }
        </div>

        <!-- Nom -->
        <p-floatlabel variant="on">
          <input
            pInputText
            id="envelopeName"
            [(ngModel)]="name"
            maxlength="100"
            class="w-full"
          />
          <label for="envelopeName">Nom de l'enveloppe</label>
        </p-floatlabel>

        <!-- Categories -->
        <div>
          <app-category-selector
            [options]="categoryOptions()"
            selectionMode="checkbox"
            [selectedIds]="selectedCategoryIds()"
            placeholder="Categories couvertes"
            (categoriesSelected)="onCategoriesSelected($event)"
          />
          <small class="text-sm text-muted-color">
            Une categorie racine inclut automatiquement ses sous-categories.
          </small>
        </div>

        <!-- Budget -->
        <p-floatlabel variant="on">
          <p-inputnumber
            inputId="budget"
            [(ngModel)]="budget"
            mode="currency"
            currency="EUR"
            locale="fr-FR"
            [minFractionDigits]="2"
            [min]="0"
          />
          <label for="budget">Budget mensuel (EUR)</label>
        </p-floatlabel>

        <!-- Rollover -->
        <div>
          <p-selectbutton
            [options]="rolloverOptions"
            [(ngModel)]="rolloverPolicy"
            optionLabel="label"
            optionValue="value"
            aria-label="Politique de report"
          />
          <small class="block mt-2 text-sm text-muted-color">
            Remise a zero : chaque mois repart du budget par defaut. Report du solde : le reste
            du mois precedent s'ajoute (ou se soustrait) au budget du mois suivant.
          </small>
        </div>

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
            [disabled]="!isValid() || submitting()"
            (onClick)="save()"
          />
        </div>
      </ng-template>
    </p-dialog>
  `,
})
export class EnvelopeDialog {
  visible = input<boolean>(false);
  mode = input<DialogMode>('create');
  envelope = input<EnvelopeResponse | null>(null);
  accounts = input<AccountResponse[]>([]);
  categoryOptions = input<TreeNode[]>([]);
  lockedAccountId = input<string | null>(null);

  saved = output<EnvelopeResponse>();
  cancelled = output<void>();

  private readonly envelopeService = inject(EnvelopeService);
  private readonly destroyRef = inject(DestroyRef);

  // Form state
  protected name = '';
  protected selectedAccountId: string | null = null;
  protected readonly selectedCategoryIds = signal<string[]>([]);
  protected budget: number | null = null;
  protected rolloverPolicy: RolloverPolicy = 'RESET';

  protected readonly submitting = signal<boolean>(false);
  protected readonly error = signal<string | null>(null);

  protected readonly rolloverOptions = [
    { value: 'RESET' as RolloverPolicy, label: 'Remise a zero' },
    { value: 'CARRY_OVER' as RolloverPolicy, label: 'Report du solde' },
  ];

  protected readonly header = computed(() =>
    this.mode() === 'edit' ? "Modifier l'enveloppe" : 'Nouvelle enveloppe',
  );

  protected readonly selectedAccount = computed(() =>
    this.accounts().find((a) => a.id === this.selectedAccountId) ?? null,
  );

  constructor() {
    effect(() => {
      const env = this.envelope();
      const locked = this.lockedAccountId();
      if (env) {
        // Edit mode: pre-fill from envelope
        this.name = env.name;
        this.selectedAccountId = env.bankAccountId;
        this.selectedCategoryIds.set(env.categories.map((c) => c.id));
        this.budget = env.defaultBudget;
        this.rolloverPolicy = env.rolloverPolicy;
      } else {
        // Create mode: reset
        this.name = '';
        this.selectedAccountId = locked ?? null;
        this.selectedCategoryIds.set([]);
        this.budget = null;
        this.rolloverPolicy = 'RESET';
      }
      this.error.set(null);
    });
  }

  protected isValid(): boolean {
    return (
      this.name.trim().length > 0 &&
      this.selectedCategoryIds().length > 0 &&
      this.budget !== null &&
      this.budget >= 0 &&
      this.selectedAccountId !== null
    );
  }

  protected onCategoriesSelected(ids: string[]): void {
    this.selectedCategoryIds.set(ids);
  }

  protected save(): void {
    if (!this.isValid()) return;

    this.submitting.set(true);
    this.error.set(null);

    const name = this.name.trim();
    const categoryIds = this.selectedCategoryIds();
    const budget = this.budget!;
    const rollover = this.rolloverPolicy;
    const env = this.envelope();

    if (this.mode() === 'edit' && env) {
      this.envelopeService
        .updateEnvelope(env.id, {
          name,
          categoryIds,
          budget,
          rolloverPolicy: rollover,
        })
        .pipe(takeUntilDestroyed(this.destroyRef))
        .subscribe({
          next: (resp) => {
            this.submitting.set(false);
            this.saved.emit(resp);
          },
          error: (err: HttpErrorResponse) => this.handleError(err),
        });
    } else {
      this.envelopeService
        .createEnvelope(this.selectedAccountId!, {
          name,
          categoryIds,
          budget,
          rolloverPolicy: rollover,
        })
        .pipe(takeUntilDestroyed(this.destroyRef))
        .subscribe({
          next: (resp) => {
            this.submitting.set(false);
            this.saved.emit(resp);
          },
          error: (err: HttpErrorResponse) => this.handleError(err),
        });
    }
  }

  private handleError(err: HttpErrorResponse): void {
    this.submitting.set(false);
    if (err.status === 403) {
      this.error.set(
        "Vous n'avez pas les droits pour modifier les enveloppes de ce compte.",
      );
    } else if (err.status === 409) {
      this.error.set(
        'Une categorie selectionnee appartient deja a une autre enveloppe de ce compte. Choisissez des categories libres.',
      );
    } else {
      this.error.set(
        "Impossible d'enregistrer l'enveloppe. Veuillez reessayer.",
      );
    }
  }
}
