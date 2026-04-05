import { ChangeDetectionStrategy, Component } from '@angular/core';
import { RouterLink, RouterLinkActive } from '@angular/router';

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
      </nav>
    </aside>
  `,
})
export class Sidebar {}
