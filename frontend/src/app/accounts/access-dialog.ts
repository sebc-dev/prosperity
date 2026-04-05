import {
  ChangeDetectionStrategy,
  Component,
  computed,
  effect,
  inject,
  input,
  output,
  signal,
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { forkJoin } from 'rxjs';
import { DialogModule } from 'primeng/dialog';
import { SelectModule } from 'primeng/select';
import { ButtonModule } from 'primeng/button';
import { MessageModule } from 'primeng/message';
import { AccountService } from './account.service';
import { AccountAccessResponse, AccountResponse, AccessLevel } from './account.types';
import { AuthService } from '../auth/auth.service';
import { UserResponse } from '../auth/auth.types';

@Component({
  selector: 'app-access-dialog',
  changeDetection: ChangeDetectionStrategy.OnPush,
  standalone: true,
  imports: [CommonModule, FormsModule, DialogModule, SelectModule, ButtonModule, MessageModule],
  template: `
    <p-dialog
      [header]="'Gerer les acces — ' + (account()?.name ?? '')"
      [visible]="visible()"
      (onHide)="visibleChange.emit(false)"
      [modal]="true"
      [closable]="true"
      [draggable]="false"
      styleClass="max-w-2xl w-full"
    >
      <div class="flex flex-col gap-4 p-6">
        <h3 class="text-sm font-semibold">Utilisateurs avec acces :</h3>

        @if (error()) {
          <p-message severity="error" [text]="error()!" />
        }

        @if (loading()) {
          <div class="text-center py-4 text-muted-color">Chargement...</div>
        } @else {
          <table class="w-full">
            <thead>
              <tr class="text-sm font-semibold text-left border-b">
                <th class="pb-2">Utilisateur</th>
                <th class="pb-2">Niveau</th>
                <th class="pb-2 w-16">Action</th>
              </tr>
            </thead>
            <tbody>
              @for (entry of accessEntries(); track entry.id) {
                <tr class="border-b">
                  <td class="py-2">{{ entry.userEmail }}</td>
                  <td class="py-2">
                    <p-select
                      [ngModel]="entry.accessLevel"
                      (ngModelChange)="onLevelChange(entry, $event)"
                      [options]="levelOptions"
                      optionLabel="label"
                      optionValue="value"
                      [disabled]="entry.userEmail === currentUserEmail() || savingRowId() === entry.id"
                      styleClass="w-32"
                    />
                  </td>
                  <td class="py-2">
                    @if (entry.userEmail !== currentUserEmail()) {
                      <p-button
                        icon="pi pi-times"
                        [text]="true"
                        severity="danger"
                        [loading]="savingRowId() === entry.id"
                        (onClick)="removeAccess(entry)"
                        [attr.aria-label]="'Retirer acces de ' + entry.userEmail"
                      />
                    }
                  </td>
                </tr>
              }
            </tbody>
          </table>

          @if (availableUsers().length > 0) {
            <div class="mt-4">
              <h3 class="text-sm font-semibold mb-2">Ajouter un utilisateur :</h3>
              <div class="flex gap-2 items-center">
                <p-select
                  [(ngModel)]="newUserId"
                  [options]="availableUsers()"
                  optionLabel="label"
                  optionValue="value"
                  placeholder="Utilisateur"
                  styleClass="flex-1"
                />
                <p-select
                  [(ngModel)]="newAccessLevel"
                  [options]="levelOptions"
                  optionLabel="label"
                  optionValue="value"
                  styleClass="w-32"
                />
                <p-button
                  icon="pi pi-plus"
                  [disabled]="!newUserId"
                  (onClick)="addUser()"
                />
              </div>
            </div>
          }
        }
      </div>

      <ng-template pTemplate="footer">
        <p-button
          label="Fermer"
          [text]="true"
          severity="secondary"
          (onClick)="visibleChange.emit(false)"
        />
      </ng-template>
    </p-dialog>
  `,
})
export class AccessDialog {
  visible = input(false);
  account = input<AccountResponse | null>(null);

  visibleChange = output<boolean>();

  private readonly accountService = inject(AccountService);
  private readonly authService = inject(AuthService);

  protected accessEntries = signal<AccountAccessResponse[]>([]);
  protected allUsers = signal<UserResponse[]>([]);
  protected loading = signal(true);
  protected error = signal<string | null>(null);
  protected savingRowId = signal<string | null>(null);

  // Add user form
  protected newUserId = '';
  protected newAccessLevel: AccessLevel = 'READ';

  protected currentUserEmail = computed(() => this.authService.user()?.email ?? '');

  protected levelOptions = [
    { label: 'Lecture', value: 'READ' },
    { label: 'Ecriture', value: 'WRITE' },
    { label: 'Admin', value: 'ADMIN' },
  ];

  protected availableUsers = computed(() => {
    const existingUserIds = new Set(this.accessEntries().map((e) => e.userId));
    return this.allUsers()
      .filter((u) => !existingUserIds.has(u.id))
      .map((u) => ({ label: u.email, value: u.id }));
  });

  constructor() {
    effect(() => {
      const acct = this.account();
      if (acct && this.visible()) {
        this.loadAccessData(acct.id);
      }
    });
  }

  private loadAccessData(accountId: string): void {
    this.loading.set(true);
    this.error.set(null);

    forkJoin([
      this.accountService.getAccessEntries(accountId),
      this.accountService.loadUsers(),
    ]).subscribe({
      next: ([entries, users]) => {
        this.accessEntries.set(entries);
        this.allUsers.set(users);
        this.loading.set(false);
      },
      error: () => {
        this.error.set('Impossible de charger les acces.');
        this.loading.set(false);
      },
    });
  }

  protected onLevelChange(entry: AccountAccessResponse, newLevel: AccessLevel): void {
    const acct = this.account();
    if (!acct) return;

    this.savingRowId.set(entry.id);
    this.accountService.setAccess(acct.id, { userId: entry.userId, accessLevel: newLevel }).subscribe({
      next: (updated) => {
        this.accessEntries.update((entries) =>
          entries.map((e) => (e.id === entry.id ? updated : e)),
        );
        this.savingRowId.set(null);
      },
      error: () => {
        this.error.set("Impossible d'enregistrer les modifications. Veuillez reessayer.");
        this.savingRowId.set(null);
      },
    });
  }

  protected addUser(): void {
    const acct = this.account();
    if (!acct || !this.newUserId) return;

    this.accountService
      .setAccess(acct.id, {
        userId: this.newUserId,
        accessLevel: this.newAccessLevel,
      })
      .subscribe({
        next: (entry) => {
          this.accessEntries.update((entries) => [...entries, entry]);
          this.newUserId = '';
          this.newAccessLevel = 'READ';
        },
        error: () => {
          this.error.set("Impossible d'ajouter l'utilisateur.");
        },
      });
  }

  protected removeAccess(entry: AccountAccessResponse): void {
    const acct = this.account();
    if (!acct) return;

    this.savingRowId.set(entry.id);
    this.accountService.removeAccess(acct.id, entry.id).subscribe({
      next: () => {
        this.accessEntries.update((entries) => entries.filter((e) => e.id !== entry.id));
        this.savingRowId.set(null);
      },
      error: (err) => {
        const msg =
          err?.status === 409
            ? 'Impossible de retirer le dernier administrateur du compte.'
            : "Impossible de retirer l'acces. Veuillez reessayer.";
        this.error.set(msg);
        this.savingRowId.set(null);
      },
    });
  }
}
