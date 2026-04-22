import { ChangeDetectionStrategy, Component, DestroyRef, inject } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { RouterLink, RouterLinkActive } from '@angular/router';
import { AccountService } from '../accounts/account.service';

@Component({
  selector: 'app-sidebar',
  imports: [RouterLink, RouterLinkActive],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <aside
      class="w-64 min-h-full bg-surface-0 border-r border-surface-200 flex flex-col"
      aria-label="Menu de navigation"
    >
      <nav class="flex flex-col gap-1 p-2 pt-4">
        <a
          routerLink="/accounts"
          routerLinkActive="bg-surface-100 text-primary font-semibold border-l-3 border-primary"
          class="flex items-center gap-3 px-3 py-2 rounded-md text-muted-color hover:bg-surface-50 transition-colors"
        >
          <i class="pi pi-wallet"></i>
          <span>Comptes</span>
        </a>
        @for (account of accounts(); track account.id) {
          <a
            [routerLink]="['/accounts', account.id, 'transactions']"
            routerLinkActive="bg-surface-100 text-primary font-semibold border-l-3 border-primary"
            class="flex items-center gap-3 px-3 py-2 pl-8 rounded-md text-muted-color hover:bg-surface-50 transition-colors text-sm"
          >
            <i class="pi pi-list"></i>
            <span>{{ account.name }}</span>
          </a>
        }
        <a
          routerLink="/categories"
          routerLinkActive="bg-surface-100 text-primary font-semibold border-l-3 border-primary"
          class="flex items-center gap-3 px-3 py-2 rounded-md text-muted-color hover:bg-surface-50 transition-colors"
        >
          <i class="pi pi-tag"></i>
          <span>Categories</span>
        </a>
        <a
          routerLink="/envelopes"
          routerLinkActive="bg-surface-100 text-primary font-semibold border-l-3 border-primary"
          class="flex items-center gap-3 px-3 py-2 rounded-md text-muted-color hover:bg-surface-50 transition-colors"
        >
          <i class="pi pi-wallet" aria-hidden="true"></i>
          <span>Enveloppes</span>
        </a>
      </nav>
    </aside>
  `,
})
export class Sidebar {
  private readonly accountService = inject(AccountService);
  private readonly destroyRef = inject(DestroyRef);

  protected readonly accounts = this.accountService.accounts;

  constructor() {
    this.accountService
      .loadAccounts()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe();
  }
}
