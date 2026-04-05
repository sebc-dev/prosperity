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
import { ReactiveFormsModule, FormBuilder, Validators } from '@angular/forms';
import { DialogModule } from 'primeng/dialog';
import { FloatLabelModule } from 'primeng/floatlabel';
import { InputTextModule } from 'primeng/inputtext';
import { SelectModule } from 'primeng/select';
import { ButtonModule } from 'primeng/button';
import { MessageModule } from 'primeng/message';
import { AccountService } from './account.service';
import { AccountResponse, AccountType } from './account.types';

@Component({
  selector: 'app-account-dialog',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    ReactiveFormsModule,
    DialogModule,
    FloatLabelModule,
    InputTextModule,
    SelectModule,
    ButtonModule,
    MessageModule,
  ],
  template: `
    <p-dialog
      [header]="dialogHeader()"
      [visible]="visible()"
      (onHide)="onHide()"
      [modal]="true"
      [closable]="true"
      [draggable]="false"
      styleClass="max-w-lg w-full"
    >
      <form [formGroup]="form" (ngSubmit)="onSave()" class="flex flex-col gap-4 p-6">
        <p-floatlabel variant="on">
          <input pInputText id="accountName" formControlName="name" class="w-full" />
          <label for="accountName">Nom du compte</label>
        </p-floatlabel>
        @if (form.controls.name.touched && form.controls.name.errors) {
          @if (form.controls.name.errors['required']) {
            <small class="text-red-500">Le nom du compte est requis</small>
          }
          @if (form.controls.name.errors['maxlength']) {
            <small class="text-red-500">Le nom ne peut pas depasser 100 caracteres</small>
          }
        }

        <p-floatlabel variant="on">
          <p-select
            id="accountType"
            formControlName="accountType"
            [options]="typeOptions"
            optionLabel="label"
            optionValue="value"
            appendTo="body"
            styleClass="w-full"
          />
          <label for="accountType">Type de compte</label>
        </p-floatlabel>

        @if (error()) {
          <p-message severity="error" [text]="error()!" />
        }
      </form>

      <ng-template pTemplate="footer">
        <div class="flex justify-end gap-2">
          <p-button label="Annuler" [text]="true" severity="secondary" (onClick)="onHide()" />
          <p-button
            [label]="loading() ? 'Enregistrement...' : 'Enregistrer le compte'"
            [loading]="loading()"
            [disabled]="form.invalid || loading()"
            (onClick)="onSave()"
          />
        </div>
      </ng-template>
    </p-dialog>
  `,
})
export class AccountDialog {
  visible = input(false);
  account = input<AccountResponse | null>(null);

  visibleChange = output<boolean>();
  saved = output<void>();

  private readonly accountService = inject(AccountService);
  private readonly fb = inject(FormBuilder);
  private readonly destroyRef = inject(DestroyRef);

  protected form = this.fb.group({
    name: ['', [Validators.required, Validators.maxLength(100)]],
    accountType: ['PERSONAL' as AccountType, Validators.required],
  });

  protected loading = signal(false);
  protected error = signal<string | null>(null);

  protected isEdit = computed(() => this.account() !== null);
  protected dialogHeader = computed(() =>
    this.isEdit() ? 'Modifier le compte' : 'Ajouter un compte',
  );

  protected typeOptions = [
    { label: 'Personnel', value: 'PERSONAL' },
    { label: 'Commun', value: 'SHARED' },
  ];

  constructor() {
    effect(() => {
      const acct = this.account();
      if (acct) {
        this.form.patchValue({ name: acct.name, accountType: acct.accountType });
      } else {
        this.form.reset({ name: '', accountType: 'PERSONAL' });
      }
      this.error.set(null);
    });
  }

  protected onSave(): void {
    if (this.form.invalid) return;
    this.loading.set(true);
    this.error.set(null);

    const { name, accountType } = this.form.getRawValue();
    const acct = this.account();

    const request$ = acct
      ? this.accountService.updateAccount(acct.id, { name: name!, accountType: accountType! })
      : this.accountService.createAccount({ name: name!, accountType: accountType! });

    request$.pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: () => {
        this.loading.set(false);
        this.visibleChange.emit(false);
        this.saved.emit();
      },
      error: () => {
        this.loading.set(false);
        this.error.set("Impossible d'enregistrer les modifications. Veuillez reessayer.");
      },
    });
  }

  protected onHide(): void {
    this.visibleChange.emit(false);
  }
}
