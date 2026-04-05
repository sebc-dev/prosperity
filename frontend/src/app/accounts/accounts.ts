import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { TableModule } from 'primeng/table';
import { ButtonModule } from 'primeng/button';
import { TagModule } from 'primeng/tag';
import { ToggleSwitchModule } from 'primeng/toggleswitch';
import { ConfirmDialogModule } from 'primeng/confirmdialog';
import { MessageModule } from 'primeng/message';
import { TooltipModule } from 'primeng/tooltip';
import { ConfirmationService } from 'primeng/api';
import { AccountService } from './account.service';
import { AccountResponse } from './account.types';
import { AccountDialog } from './account-dialog';

@Component({
  selector: 'app-accounts',
  changeDetection: ChangeDetectionStrategy.OnPush,
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    TableModule,
    ButtonModule,
    TagModule,
    ToggleSwitchModule,
    ConfirmDialogModule,
    MessageModule,
    TooltipModule,
    AccountDialog,
  ],
  providers: [ConfirmationService],
  template: `
    <div class="p-8">
      <!-- Header row -->
      <div class="flex items-center justify-between mb-6">
        <h1 class="text-2xl font-semibold">Comptes bancaires</h1>
        <p-button
          label="Ajouter un compte"
          icon="pi pi-plus"
          (onClick)="openCreateDialog()"
        />
      </div>

      <!-- Archive toggle -->
      <div class="flex items-center justify-end gap-2 mb-4">
        <label for="archiveToggle" class="text-sm">Afficher les archives</label>
        <p-toggleswitch
          [(ngModel)]="includeArchived"
          (onChange)="onToggleArchived()"
          inputId="archiveToggle"
          aria-label="Afficher les comptes archives"
        />
      </div>

      <!-- Error message -->
      @if (error()) {
        <p-message severity="error" [text]="error()!" styleClass="mb-4 w-full" />
      }

      <!-- Empty state -->
      @if (!loading() && accounts().length === 0) {
        <div role="status" class="text-center py-12">
          <h2 class="text-lg font-semibold mb-2">Aucun compte</h2>
          <p class="text-muted-color mb-4">Creez votre premier compte bancaire pour commencer a suivre vos finances.</p>
          <p-button label="Ajouter un compte" icon="pi pi-plus" (onClick)="openCreateDialog()" />
        </div>
      }

      <!-- Table -->
      @if (accounts().length > 0) {
        <p-table
          [value]="accounts()"
          [stripedRows]="true"
          [sortField]="'name'"
          [sortOrder]="1"
          styleClass="p-datatable-sm"
        >
          <ng-template pTemplate="header">
            <tr>
              <th pSortableColumn="name">Nom <p-sortIcon field="name" /></th>
              <th>Type</th>
              <th pSortableColumn="balance">Solde <p-sortIcon field="balance" /></th>
              <th>Statut</th>
              <th>Actions</th>
            </tr>
          </ng-template>
          <ng-template pTemplate="body" let-account>
            <tr [class.text-muted-color]="account.archived">
              <td>{{ account.name }}</td>
              <td>
                <p-tag
                  [value]="account.accountType === 'SHARED' ? 'Commun' : 'Personnel'"
                  [severity]="account.accountType === 'SHARED' ? 'info' : 'secondary'"
                />
              </td>
              <td class="font-tabular-nums">
                {{ account.balance | number:'1.2-2':'fr-FR' }} {{ account.currency }}
              </td>
              <td>
                <p-tag
                  [value]="account.archived ? 'Archive' : 'Actif'"
                  [severity]="account.archived ? 'warn' : 'success'"
                />
              </td>
              <td>
                <div class="flex gap-1">
                  @if (account.currentUserAccessLevel === 'WRITE' || account.currentUserAccessLevel === 'ADMIN') {
                    <p-button
                      icon="pi pi-pencil"
                      [text]="true"
                      severity="secondary"
                      [pTooltip]="'Modifier ' + account.name"
                      (onClick)="openEditDialog(account)"
                      [attr.aria-label]="'Modifier ' + account.name"
                    />
                  }
                  @if (account.currentUserAccessLevel === 'ADMIN' && account.accountType === 'SHARED') {
                    <p-button
                      icon="pi pi-users"
                      [text]="true"
                      severity="secondary"
                      [pTooltip]="'Gerer les acces de ' + account.name"
                      (onClick)="openAccessDialog(account)"
                      [attr.aria-label]="'Gerer les acces de ' + account.name"
                    />
                  }
                  @if (account.currentUserAccessLevel === 'ADMIN') {
                    @if (account.archived) {
                      <p-button
                        icon="pi pi-replay"
                        [text]="true"
                        severity="secondary"
                        pTooltip="Desarchiver"
                        (onClick)="unarchive(account)"
                        [attr.aria-label]="'Desarchiver ' + account.name"
                      />
                    } @else {
                      <p-button
                        icon="pi pi-inbox"
                        [text]="true"
                        severity="danger"
                        [pTooltip]="'Archiver ' + account.name"
                        (onClick)="confirmArchive(account)"
                        [attr.aria-label]="'Archiver ' + account.name"
                      />
                    }
                  }
                </div>
              </td>
            </tr>
          </ng-template>
        </p-table>
      }

      <!-- Confirm dialog -->
      <p-confirmdialog />

      <!-- Create/Edit dialog -->
      <app-account-dialog
        [visible]="dialogVisible()"
        [account]="editingAccount()"
        (visibleChange)="dialogVisible.set($event)"
        (saved)="onDialogSaved()"
      />
    </div>
  `,
})
export class Accounts {
  private readonly accountService = inject(AccountService);
  private readonly confirmationService = inject(ConfirmationService);

  protected includeArchived = false;
  protected loading = signal(true);
  protected error = signal<string | null>(null);

  protected accounts = this.accountService.accounts;

  // Dialog state
  protected dialogVisible = signal(false);
  protected editingAccount = signal<AccountResponse | null>(null);

  // Access dialog state (to be implemented in Plan 09)
  protected accessDialogVisible = signal(false);
  protected accessDialogAccount = signal<AccountResponse | null>(null);

  constructor() {
    this.loadData();
  }

  protected loadData(): void {
    this.loading.set(true);
    this.error.set(null);
    this.accountService.loadAccounts(this.includeArchived).subscribe({
      next: () => this.loading.set(false),
      error: () => {
        this.loading.set(false);
        this.error.set('Impossible de charger les comptes. Verifiez votre connexion et reessayez.');
      },
    });
  }

  protected onToggleArchived(): void {
    this.loadData();
  }

  protected openCreateDialog(): void {
    this.editingAccount.set(null);
    this.dialogVisible.set(true);
  }

  protected openEditDialog(account: AccountResponse): void {
    this.editingAccount.set(account);
    this.dialogVisible.set(true);
  }

  protected onDialogSaved(): void {
    this.loadData();
  }

  protected confirmArchive(account: AccountResponse): void {
    this.confirmationService.confirm({
      header: 'Archiver le compte',
      message: `Etes-vous sur de vouloir archiver "${account.name}" ? Le compte sera masque mais ses donnees seront conservees.`,
      acceptLabel: 'Archiver',
      rejectLabel: 'Annuler',
      accept: () => {
        this.accountService.updateAccount(account.id, { archived: true }).subscribe({
          next: () => this.loadData(),
          error: () => this.error.set('Impossible de charger les comptes. Verifiez votre connexion et reessayez.'),
        });
      },
    });
  }

  protected unarchive(account: AccountResponse): void {
    this.accountService.updateAccount(account.id, { archived: false }).subscribe({
      next: () => this.loadData(),
      error: () => this.error.set('Impossible de charger les comptes. Verifiez votre connexion et reessayez.'),
    });
  }

  // TODO(Plan 09): implement access management dialog
  protected openAccessDialog(account: AccountResponse): void {
    this.accessDialogAccount.set(account);
    this.accessDialogVisible.set(true);
  }
}
